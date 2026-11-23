#!/usr/bin/env python3
"""Parse OCR results into structured events (theme/section/sub/entry).

Reads ocr_raw.json (from ocr_all.py), writes events.json: a flat ordered list of
  {type:'theme'|'section'|'sub'|'entry', page, y, ru, en, tr?, num?}

Layout assumptions (the "Словарь-минимум с логической структурой" book):
  - 3-column page: Russian headword (left, x<0.20W), English translation (mid),
    transcription (right / in brackets).
  - Numbered subsection headers "N. ..." ; section headers contain
    Глаголы/Бытовые/Рабочие ; running header + title sit at y<0.10H (skipped).
  - Entries in dense regions are recovered via pending/trailing logic:
    a translation line with no Russian headword attaches to the current entry if it
    still lacks a translation, otherwise it is queued (pending) for the next headword.

Usage:
    python parse6.py --input ocr_raw.json --output events.json
"""
import argparse, json, re, os, sys
import numpy as np
from PIL import Image
try:
    from scipy import ndimage
    _HAS_SCIPY=True
except ImportError:
    _HAS_SCIPY=False

def cyr(t): return bool(re.search('[А-Яа-яЁё]', t))
def lat(t): return bool(re.search('[A-Za-z]', t))
def alnum(t): return any(ch.isalnum() for ch in t)
def has_bracket(t): return '[' in t or ']' in t
TITLE_KEYS=['Словарь','минимум','структур','логическ','лозическ','лоzической',
            'сирукmур','спрукиур','сирукиур','сируктурой']
SECTION_KEYS=['Глаголы','Бытовые','Рабочие']
def is_title(t): return any(k in t for k in TITLE_KEYS)

def page_number(items,H):
    c=[(it['y0'],int(it['text'])) for it in items
       if re.fullmatch(r'\d{1,3}', it['text'].strip()) and it['y0']>0.78*H and it['ink']>0.08]
    return sorted(c)[-1][1] if c else None

NUM_HEAD=re.compile(r'^\s*(\d{1,2})\s*[\.\)]?\s*$')
NUM_HEAD_T=re.compile(r'^\s*(\d{1,2})\s*[\.\)\s]\s*(\D.*?)\s*$')
def numbox(t):
    t=t.strip()
    m=NUM_HEAD_T.match(t)
    if m and (cyr(m.group(2)) or lat(m.group(2))): return int(m.group(1)), m.group(2)
    if NUM_HEAD.match(t): return int(NUM_HEAD.match(t).group(1)), None
    return None,None
def starts_with_number(t):
    m=re.match(r'^\s*(\d{1,2})\s*[\.\)\s]', t)
    return int(m.group(1)) if m else None
def is_pagenum_stray(it,H,t):
    # pure 1-3 digit number at the very bottom of the page = page number, not a subsection idx
    return re.fullmatch(r'\d{1,3}', t) and it['y0']>0.90*H

def clean(t):
    t=t.strip().replace('`','')
    t=re.sub(r'\s+',' ',t)
    return t.strip(' ;:,.\'"')

# cache image arrays per file for stroke-width scoring
_IMG_CACHE={}
def get_arr(path):
    if path not in _IMG_CACHE:
        im=Image.open(path).convert("L"); _IMG_CACHE[path]=np.asarray(im)
    return _IMG_CACHE[path]

def stroke_of(path,box):
    """Half the thickest stroke width in the box = max of the Euclidean distance
    transform of the ink mask. Scale- and padding-robust: it measures the widest
    stroke, not total area, so it is independent of how tight the OCR box is.
    Returns None for non-text blobs (filtered to a plausible text-stroke range)."""
    if not _HAS_SCIPY: return None
    try:
        arr=get_arr(path); H,W=arr.shape
    except Exception: return None
    x0,y0,x1,y1=box; x0=max(0,int(x0));y0=max(0,int(y0));x1=min(W,int(x1));y1=min(H,int(y1))
    c=arr[y0:y1,x0:x1]
    if c.size==0 or c.shape[0]<3 or c.shape[1]<3: return None
    m=(c<140).astype(np.uint8)
    if m.sum()<5: return None
    st=float(ndimage.distance_transform_edt(m).max())
    if st<1.0 or st>12.0: return None     # reject garbage blobs / page edges
    return st

def bbox_of(items):
    xs0=min(i['x0'] for i in items); ys0=min(i['y0'] for i in items)
    xs1=max(i['x1'] for i in items); ys1=max(i['y1'] for i in items)
    return (xs0,ys0,xs1,ys1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', default='ocr_raw.json')
    ap.add_argument('--output', default='events.json')
    ap.add_argument('--img-dir', default='.',
                   help='directory with the source images (for boldness scoring)')
    args=ap.parse_args()
    IMG_DIR=args.img_dir
    d=json.load(open(args.input,encoding="utf-8"))

    pages=[]
    for f,pg in d.items():
        pn=page_number(pg['items'],pg['H'])
        pages.append({'file':f,'page':pn,'W':pg['W'],'H':pg['H'],'items':pg['items']})
    # order by printed page number (fallback: filename) — filename order matters if no page numbers
    pages.sort(key=lambda x:(x['page'] if x['page'] is not None else 9999, x['file']))

    LINE_GAP=20
    events=[]
    for p in pages:
        items=p['items']; W=p['W']; H=p['H']; page=p['page']
        its=[it for it in items if (alnum(it['text']) or it['ink']>0.05) and not is_title(it['text'])]
        its=sorted(its,key=lambda x:(x['y0'],x['x0']))
        # cluster into visual lines by consecutive Y gap
        lines=[]; cur=[its[0]] if its else []
        for it in its[1:]:
            if it['y0']-cur[-1]['y0']>LINE_GAP:
                lines.append(cur); cur=[it]
            else: cur.append(it)
        if cur: lines.append(cur)

        def classify(line):
            ru=[]; en=[]; tr=[]; num=None; sec=False; head=None
            for it in line:
                t=it['text'].strip()
                if is_title(t): continue
                if is_pagenum_stray(it,H,t): continue
                if any(k in t for k in SECTION_KEYS) and it['x0']>0.18*W:
                    sec=True; ru.append((it['x0'],t)); continue
                nb,rest=numbox(t)
                if nb is not None and it['ink']>0.08 and it['x0']>0.10*W and not is_pagenum_stray(it,H,t):
                    num=nb
                    if rest: ru.append((it['x0'],rest))
                    continue
                if has_bracket(t):
                    tr.append((it['x0'],t,it)); continue
                if it['x0']<0.62*W and cyr(t) and starts_with_number(t) is None:
                    ru.append((it['x0'],t))
                    if head is None and it['x0']<0.20*W: head=it
                    continue
                if 0.26*W<=it['x0']<0.64*W and lat(t) and not cyr(t):
                    en.append((it['x0'],t,it)); continue
                if it['x0']>=0.64*W and it['ink']>0.1 and (lat(t) or cyr(t)):
                    tr.append((it['x0'],t,it)); continue
            return ru,en,tr,num,sec,head

        L=[(line,classify(line)) for line in lines]

        def lookahead_en(i,base_y):
            for j in range(i+1,len(L)):
                yj=min(it['y0'] for it in L[j][0])
                if yj-base_y>170: break
                ruj,enj,trj,numj,secj,_h=L[j][1]
                if enj and not ruj and numj is None and not secj:
                    consumed.add(j); return enj,yj,j
                if ruj or numj is not None or secj: break
            return None,None,None

        state={'cur':None}; pending={'en':[],'tr':[],'ru':[]}; consumed=set()
        def flush():
            c=state['cur']
            if not c:
                state['cur']=None; return
            keep=(c.get('ru') and c.get('en')) or (c.get('ru') and not c.get('en') and has_bracket(c.get('tr','')))
            if not keep:
                state['cur']=None; return
            # stroke width = thickest stroke across the ru headword and the en
            # translation (both are bold when the entry is a "главное слово").
            # Transcription is NOT measured — it is never bold on the page.
            path=os.path.join(IMG_DIR,p['file'])
            rs=None
            h=c.get('head')
            if h is not None:
                rs=stroke_of(path,(h['x0'],h['y0'],h['x1'],h['y1']))
            es=stroke_of(path,bbox_of(c.get('en_items',[]))) if c.get('en_items') else None
            c['stroke']=max([v for v in (rs,es) if v is not None],default=None)
            c['stroke_base']=rs    # ru-head raw stroke, for per-page median
            events.append(c)
            state['cur']=None

        for i,(line,(ru,en,tr,num,sec,head)) in enumerate(L):
            y=min(it['y0'] for it in line)
            if y<0.10*H: continue                      # running header / title zone
            if i in consumed: continue
            if not ru and not en and not tr and not sec and num is None: continue
            if sec:
                flush()
                ru_txt=clean(" ".join(x[1] for x in sorted(ru)))
                en_txt=clean(" ".join(x[1] for x in sorted(pending['en']+en)))
                if not en_txt:
                    la,yj,j=lookahead_en(i,y)
                    if la: en_txt=clean(" ".join(x[1] for x in sorted(la)))
                pending={'en':[],'tr':[],'ru':[]}
                if ru_txt.strip() in ('Глаголы','Глааолы','Глааолъ','Глаголъ'):
                    events.append({'type':'theme','page':page,'y':y,'ru':'Глаголы','en':en_txt or 'Verbs'})
                else:
                    events.append({'type':'section','page':page,'y':y,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue
            if num is not None:
                flush()
                ru_txt=clean(" ".join(x[1] for x in sorted(ru+pending['ru'])))
                en_txt=clean(" ".join(x[1] for x in sorted(pending['en']+en)))
                pending={'en':[],'tr':[],'ru':[]}
                if not ru_txt and events and events[-1].get('type')=='entry':
                    prev=events.pop(); ru_txt=prev.get('ru',''); en_txt=prev.get('en','')
                elif not en_txt:
                    la,yj,j=lookahead_en(i,y)
                    if la: en_txt=clean(" ".join(x[1] for x in sorted(la)))
                if ru_txt or en_txt:
                    events.append({'type':'sub','page':page,'y':y,'num':num,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue
            if ru and any(x[0]<0.20*W for x in ru):
                flush()
                en_items=[tup[2] for tup in (pending['en']+en)]
                state['cur']={'type':'entry','page':page,'y':y,
                              'ru':clean(" ".join(x[1] for x in sorted(ru))),
                              'en':clean(" ".join(x[1] for x in sorted(pending['en']+en))),
                              'tr':clean(" ".join(x[1] for x in sorted(pending['tr']+tr))),
                              'head':head,'en_items':en_items}
                pending={'en':[],'tr':[],'ru':[]}; continue
            if en or tr:
                c=state['cur']
                if c is not None and not c.get('en') and en:
                    c['en']=clean(c['en']+" "+" ".join(x[1] for x in sorted(en)))
                    c.setdefault('en_items',[]).extend(tup[2] for tup in en)
                    if tr: c['tr']=clean(c['tr']+" "+" ".join(x[1] for x in sorted(tr)))
                elif c is not None and not c.get('tr') and tr and not en:
                    c['tr']=clean(c['tr']+" "+" ".join(x[1] for x in sorted(tr)))
                else:
                    if en: pending['en'].extend(en)
                    if tr: pending['tr'].extend(tr)
        flush()

    events.sort(key=lambda e:(e['page'] if e['page'] else 9999, e['y']))
    json.dump(events,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    n={k:sum(1 for e in events if e['type']==k) for k in ('theme','section','sub','entry')}
    print(f"[parse] {n} -> {args.output}")

if __name__=='__main__':
    main()
