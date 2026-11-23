#!/usr/bin/env python3
"""Assemble the structured dictionary tree from parsed events.

Reads events.json (from parse6.py), writes dictionary.json:
  {book, theme, sections[{section, subsections[{number, subsection, subsection_ocr, entries}]}]}

Section/subsection titles come from OCR by default. To override with clean canonical
titles for a known part of the book, pass --canonical CANONICAL_JSON (see
canonical_verbs.json for the format):

    {"sections":[{"ru":"...","en":"...","subsections":[{"num":1,"ru":"...","en":"..."}, ...]}, ...]

Sections are matched by ORDER (nth section in the file ↔ nth in canonical);
subsections by num within that section.

Usage:
    python build_json.py --input events.json --output dictionary.json [--canonical canonical_verbs.json]
"""
import argparse, json, re

EN_FIX={'g0':'go','G0':'go','CrOSS':'cross','Jast':'last','tumn':'turn','IOW':'row',
        'WAnZ':"one's","won's":"one's",'WAIZ':"ways",'mam':'man','rard':'raɪd',
        'go On':'go on','g0 On':'go on'}
def fix_en(s):
    for k,v in EN_FIX.items(): s=s.replace(k,v)
    return re.sub(r'\s+',' ',s).strip(' ;:,.\'"')

def fix_ru(s):
    s=re.sub(r'^\d+\s*','',s)                 # leading stray digit
    s=re.sub(r'\s+\d+(?:\s+\d+)*\s*$','',s)   # trailing stray digits
    if '(ся' in s and '(ся)' not in s: s=s.replace('(ся','(ся)')
    s=s.replace('(ся:','(ся)').replace('(ся.)','(ся)')
    s=re.sub(r'\(\+прил[^\)]*\)','(+прил.)',s)     # "(+прил:)" etc → "(+прил.)"
    s=re.sub(r'\(\+adj[^\)]*\)','(+adj.)',s)
    if '(+прил' in s and '(+прил.)' not in s: s=s.replace('(+прил','(+приl.)').replace('(+приl.)','(+прил.)')
    if '(+adj' in s and '(+adj.)' not in s: s=s.replace('(+adj','(+adj.)')
    s=s.replace('):)',')')
    s=re.sub(r'\s+',' ',s).strip(' ;:,.\'"')
    return s.lower()                          # Russian headwords → lowercase

def load_canonical(path):
    if not path: return None
    data=json.load(open(path,encoding="utf-8"))
    secs=[]
    for s in data['sections']:
        subs={sub['num']:{"ru":sub['ru'],"en":sub['en']} for sub in s.get('subsections',[])}
        secs.append({"ru":s['ru'],"en":s['en'],"subs":subs})
    return secs

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', default='events.json')
    ap.add_argument('--output', default='dictionary.json')
    ap.add_argument('--canonical', default=None, help='optional clean titles overlay')
    ap.add_argument('--book', default='Словарь-минимум с логической структурой')
    args=ap.parse_args()

    events=json.load(open(args.input,encoding="utf-8"))
    canon=load_canonical(args.canonical)
    events.sort(key=lambda e:(e.get('page') or 9999, e.get('y',0)))

    # Per-page median of the ru-head stroke (base/regular text). Bold words are
    # detected as outliers RELATIVE to this median, so the threshold is
    # scale-independent across photos of different resolution/crop.
    from statistics import median as _median
    page_med={}
    for e in events:
        if e.get('type')=='entry':
            sb=e.get('stroke_base')
            if sb is not None and 1.0<=sb<=12.0:
                page_med.setdefault(e.get('page'),[]).append(sb)
    page_med={pg:_median(v) for pg,v in page_med.items() if v}

    tree={"book":args.book,"theme":{"ru":"Глаголы","en":"Verbs"},"sections":[]}
    cur_sec=None; cur_sec_obj=None; cur_sub_obj=None; order=0
    BOLD_RATIO=1.30   # stroke/max(ru,en) divided by page-median ru stroke → bold

    for e in events:
        t=e['type']
        if t=='theme':
            tree['theme']={"ru":e.get('ru','Глаголы'),"en":e.get('en','Verbs')}
        elif t=='section':
            cur_sec=0 if cur_sec is None else cur_sec+1
            sec_canon=canon[cur_sec] if canon and cur_sec<len(canon) else None
            title={"ru":sec_canon['ru'],"en":sec_canon['en']} if sec_canon else {"ru":e.get('ru',''),"en":e.get('en','')}
            cur_sec_obj={"section":title,"subsections":[]}
            tree['sections'].append(cur_sec_obj); cur_sub_obj=None
        elif t=='sub':
            if cur_sec_obj is None:
                cur_sec=0 if cur_sec is None else cur_sec
                cur_sec_obj={"section":{"ru":e.get('ru',''),"en":e.get('en','')},"subsections":[]}
                tree['sections'].append(cur_sec_obj)
            num=e.get('num',1)
            sub_canon=None
            if canon and cur_sec is not None and cur_sec<len(canon):
                sub_canon=canon[cur_sec]['subs'].get(num)
            title={"ru":sub_canon['ru'],"en":sub_canon['en']} if sub_canon else {"ru":e.get('ru',''),"en":e.get('en','')}
            cur_sub_obj={"number":num,"subsection":title,
                         "subsection_ocr":{"ru":e.get('ru',''),"en":e.get('en','')},
                         "entries":[]}
            cur_sec_obj['subsections'].append(cur_sub_obj)
        elif t=='entry':
            ru=fix_ru(e.get('ru','')); en=fix_en(e.get('en','')); tr=e.get('tr','')
            if not ru and not en: continue
            st=e.get('stroke'); med=page_med.get(e.get('page'))
            ratio=(st/med) if (st and med) else None
            # is_main: the bold "главное слово группы". Boldness is measured on the
            # pixels of BOTH the Russian and the English word (transcription is never
            # bold), as the thickest stroke width normalized per page.
            is_main = ratio is not None and ratio>=BOLD_RATIO
            entry={"order":order,"page":e.get('page'),"ru":ru,"en":en,
                   "transcription":tr,"is_main":bool(is_main)}
            order+=1
            if cur_sub_obj is not None: cur_sub_obj['entries'].append(entry)

    json.dump(tree,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    ne=sum(len(ss['entries']) for s in tree['sections'] for ss in s['subsections'])
    print(f"[build] sections={len(tree['sections'])} subsections={sum(len(s['subsections']) for s in tree['sections'])} entries={ne} -> {args.output}")

if __name__=='__main__':
    main()
