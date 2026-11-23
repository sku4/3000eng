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
def is_lat_noise(t):
    """OCR noise fragment that merely looks Latin: carries a digit, is a bare
    single letter (not a real word), a mixed-case 2-letter blob like "Nn", or
    holds stray symbols. Real English translations are lowercase alphabetic
    words (optionally with hyphen/apostrophe). Used to keep page-margin crud
    out of the en column. A multi-word token (with internal spaces) is kept —
    clean_en in build_json filters it per word."""
    c=t.strip(" ;:,.\"'`")
    if not c: return True
    if re.search(r'\s', c): return False     # multi-word box → keep, filter later
    if re.search(r'\d', c): return True
    if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]?|[A-Za-z]", c): return True
    if len(c)==1 and c not in ('a','I','O'): return True
    if len(c)==2 and c[0].isupper() and c[1].islower(): return True
    return False
TITLE_KEYS=['Словарь','минимум','структур','сирукmур','спрукиур','сирукиур','сируктурой']
# Note: do NOT add 'логическ' here — it matches real dictionary words like
# "Биологический", "Технологический", "Психологический" and eats their headers.
# The book title row is already skipped by the y<0.10·H running-header zone and
# by the keys above.
SECTION_KEYS=['Глаголы','Бытовые','Рабочие']
# Part-of-speech themes. Глаголы matched exactly (section titles like "Глаголы
# стадии" must NOT be treated as theme); Прилагательные/Существительные matched
# as substrings (no section title contains them).
THEME_RU_VERBS={'Глаголы','Глааолы','Глааолъ','Глаголъ'}
THEME_RU_SUB=['Прилагательные','Существительные']
THEME_EN={'Adjectives','Nouns','Verbs'}
def is_title(t): return any(k in t for k in TITLE_KEYS)
def is_theme(ru_txt,en_txt):
    return (ru_txt in THEME_RU_VERBS) or any(k in ru_txt for k in THEME_RU_SUB) or (en_txt in THEME_EN)

def page_number(items,H):
    c=[(it['y0'],int(it['text'])) for it in items
       if re.fullmatch(r'\d{1,3}', it['text'].strip()) and it['y0']>0.78*H and it['ink']>0.08]
    return sorted(c)[-1][1] if c else None

NUM_HEAD=re.compile(r'^\s*(\d{1,2})\s*[\.\)]?\s*$')
NUM_HEAD_T=re.compile(r'^\s*(\d{1,2})\s*[\.\)\s]\s*(\D.*?)\s*$')
def numbox(t):
    t=t.strip()
    m=NUM_HEAD_T.match(t)
    if m and (cyr(m.group(2)) or lat(m.group(2))) and int(m.group(1))>=1: return int(m.group(1)), m.group(2)
    m2=NUM_HEAD.match(t)
    if m2 and int(m2.group(1))>=1: return int(m2.group(1)), None
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
            items=sorted(line,key=lambda x:x['x0'])
            for idx,it in enumerate(items):
                t=it['text'].strip()
                if not t or is_title(t) or is_pagenum_stray(it,H,t): continue
                if any(k in t for k in SECTION_KEYS) and it['x0']>0.18*W:
                    sec=True; ru.append((it['x0'],t)); continue
                # subsection number: only the leading (leftmost) token of the line,
                # so a stray digit buried in a centered title ("Эмоция … 1 …") can't
                # masquerade as a subsection index.
                if idx==0:
                    nb,rest=numbox(t)
                    # x0 gate is just a left-margin guard; real subsection headers
                    # may sit as far left as the entry column (~0.07·W), so use a
                    # loose 0.05·W. The leftmost-token + numbox-regex + ink checks
                    # are what actually prevent false subsection numbers.
                    if nb is not None and it['ink']>0.08 and it['x0']>0.05*W:
                        num=nb
                        if rest: ru.append((it['x0'],rest))
                        continue
                # transcription is always bracketed on the page; a bare Latin word
                # in the right column (e.g. "Ability" of "Absence of Ability") is a
                # wrapped translation, NOT transcription. OCR often bundles the en
                # word and its transcription into one box ("Colour [kАlэ]"), so split
                # the bracketed part from any leading en/ru word.
                if has_bracket(t):
                    brackets=re.findall(r'\[[^\]]*\]',t)
                    rest=re.sub(r'\[[^\]]*\]',' ',t).strip(' ;:,.\'"')
                    if rest:
                        if cyr(rest):
                            ru.append((it['x0'],rest))
                            if head is None: head=it
                        elif lat(rest) and not is_lat_noise(rest):
                            en.append((it['x0'],rest,it))
                    for b in brackets:
                        tr.append((it['x0'],b,it))
                    continue
                if cyr(t) and starts_with_number(t) is None:
                    ru.append((it['x0'],t))
                    if head is None: head=it     # ru headword (any column) for stroke scoring
                    continue
                if lat(t) and not cyr(t):
                    if not is_lat_noise(t):
                        en.append((it['x0'],t,it))
                    continue
                # stray digits / right-column cyr noise: ignore
            return ru,en,tr,num,sec,head

        L=[(line,classify(line)) for line in lines]

        # Auto-detect the entry (left) column on this page = the densest cyr-x bin.
        # Robust across photos of different scale/crop and across book parts where
        # headwords sit at different x (verbs vs adjectives). Bold group headwords
        # that are centered are caught separately via the transcription rule.
        import collections as _coll
        _cyr_xs=[it['x0'] for it in items if cyr(it['text'].strip()) and it['x0']<0.30*W]
        _bw=0.04*W
        if _cyr_xs:
            _bins=[int(x//_bw) for x in _cyr_xs]
            entry_x=_coll.Counter(_bins).most_common(1)[0][0]*_bw
        else:
            entry_x=0.0
        def in_entry_col(ru): return bool(ru) and any(x[0] < entry_x+_bw for x in ru)

        def lookahead_en(i,base_y):
            for j in range(i+1,len(L)):
                yj=min(it['y0'] for it in L[j][0])
                if yj-base_y>170: break
                ruj,enj,trj,numj,secj,_h=L[j][1]
                if enj and not ruj and numj is None and not secj and not trj:
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

            ru_txt=clean(" ".join(x[1] for x in sorted(ru)))
            en_txt=clean(" ".join(x[1] for x in sorted(pending['en']+en)))

            # 1) part-of-speech theme (Прилагательные / Существительные / Глаголы)
            if not sec and num is None and is_theme(ru_txt,en_txt):
                flush(); pending={'en':[],'tr':[],'ru':[]}
                events.append({'type':'theme','page':page,'y':y,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue

            # An entry line: ru in the entry (left) column, OR a centered ru+en pair
            # carrying a transcription = bold group headword (Цвет/Colour [..]).
            # On a real entry line any digit is noise, not a subsection number.
            is_entry_line = in_entry_col(ru) or (bool(tr) and ru and en)
            if is_entry_line and num is not None and not sec:
                num=None

            # 2) subsection header "N. Title" (numbered, not an entry line)
            if num is not None:
                flush()
                ru_txt=clean(" ".join(x[1] for x in sorted(ru+pending['ru'])))
                en_txt=clean(" ".join(x[1] for x in sorted(pending['en']+en)))
                pending={'en':[],'tr':[],'ru':[]}
                if not en_txt:
                    la,_,_=lookahead_en(i,y)
                    if la: en_txt=clean(" ".join(x[1] for x in sorted(la)))
                if ru_txt or en_txt:
                    events.append({'type':'sub','page':page,'y':y,'num':num,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue

            # 3) verbs section keyword (compat — "Глаголы стадии" etc.)
            if sec:
                flush()
                ru_txt=clean(" ".join(x[1] for x in sorted(ru)))
                en_txt=clean(" ".join(x[1] for x in sorted(pending['en']+en)))
                if not en_txt:
                    la,_,_=lookahead_en(i,y)
                    if la: en_txt=clean(" ".join(x[1] for x in sorted(la)))
                pending={'en':[],'tr':[],'ru':[]}
                events.append({'type':'section','page':page,'y':y,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue

            # 4) entry (left-column ru, or centered bold pair with transcription)
            if is_entry_line:
                flush()
                own_en=clean(" ".join(x[1] for x in sorted(en)))
                if own_en:
                    use_en=own_en; en_items=[tup[2] for tup in en]
                else:
                    use_en=clean(" ".join(x[1] for x in sorted(pending['en'])))
                    en_items=[tup[2] for tup in pending['en']]
                state['cur']={'type':'entry','page':page,'y':y,
                              'ru':clean(" ".join(x[1] for x in sorted(ru))),
                              'en':use_en,
                              'tr':clean(" ".join(x[1] for x in sorted(pending['tr']+tr))),
                              'head':head,'en_items':en_items}
                pending={'en':[],'tr':[],'ru':[]}; continue

            # 5) centered cyr header without number/transcription = section title.
            # Flush + clear pending so the title's en does not leak into the next
            # entry. (build_json infers section boundaries by subsection-number
            # reset, so the emitted section event is mostly a side effect.)
            if ru:
                # A cyr line carrying a single lowercase English word, with no
                # transcription and not in the entry column, is a misclustered
                # entry: OCR jitter split one visual line across two y-clusters
                # (e.g. "свободный, вакантный / vacant / [..]" → "свободный"
                # cluster + "вакантный vacant" cluster). Real section titles carry
                # multi-word or Title-case en, so this never catches them.
                if en_txt and len(en_txt.split())==1 and en_txt.islower() and en_txt.isalpha():
                    flush()
                    state['cur']={'type':'entry','page':page,'y':y,
                                  'ru':ru_txt,'en':en_txt,'tr':'',
                                  'head':head,'en_items':[tup[2] for tup in en]}
                    pending={'en':[],'tr':[],'ru':[]}; continue
                flush()
                if not en_txt:
                    la,_,_=lookahead_en(i,y)
                    if la: en_txt=clean(" ".join(x[1] for x in sorted(la)))
                pending={'en':[],'tr':[],'ru':[]}
                events.append({'type':'section','page':page,'y':y,'ru':ru_txt,'en':en_txt})
                state['cur']=None; continue

            # 6) trailing en/tr (dense regions: translation/transcription on a line
            # below the ru headword)
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
                continue
            # 7) noise line: clear pending so it does not leak into the next entry
            pending={'en':[],'tr':[],'ru':[]}
        flush()

    events.sort(key=lambda e:(e['page'] if e['page'] else 9999, e['y']))
    json.dump(events,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    n={k:sum(1 for e in events if e['type']==k) for k in ('theme','section','sub','entry')}
    print(f"[parse] {n} -> {args.output}")

if __name__=='__main__':
    main()
