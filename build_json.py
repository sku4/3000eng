#!/usr/bin/env python3
"""Assemble the structured dictionary tree from parsed events.

Reads events.json (from parse6.py), writes dictionary.json:
  {book, themes:[{theme, sections[{section, subsections[{number, subsection, entries}]}]}]}

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
    """Load a clean-titles overlay. New format carries a `theme` field so the
    overlay is applied only to the matching part of speech (Прилагательные vs
    Глаголы). Old canonical files without `theme` match any theme (back-compat)."""
    if not path: return None
    data=json.load(open(path,encoding="utf-8"))
    th=data.get('theme') or {}
    secs=[]
    for s in data['sections']:
        subs={sub['num']:{"ru":sub['ru'],"en":sub['en']} for sub in s.get('subsections',[])}
        secs.append({"ru":s['ru'],"en":s['en'],"subs":subs})
    return {"theme_ru":th.get('ru'),"theme_en":th.get('en'),"sections":secs}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', default='events.json')
    ap.add_argument('--output', default='dictionary.json')
    ap.add_argument('--canonical', default=None, help='optional clean-titles overlay (per-theme)')
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

    BOLD_RATIO=1.30   # stroke/max(ru,en) divided by page-median ru stroke → bold

    themes=[]; cur_theme=None; cur_theme_obj=None
    cur_sec_obj=None; cur_sub_obj=None; order=0
    sec_idx=-1; prev_sub_num=None
    pending_sec=None     # most recent centered section title from OCR (fallback)

    def canon_for(theme_ru):
        if not canon: return None
        if canon['theme_ru'] is None: return canon            # back-compat (no theme)
        return canon if canon['theme_ru']==theme_ru else None

    for e in events:
        t=e['type']
        if t=='theme':
            cur_theme=e.get('ru',''); cur_theme_en=e.get('en','')
            cur_theme_obj={"theme":{"ru":cur_theme,"en":cur_theme_en},"sections":[]}
            themes.append(cur_theme_obj)
            cur_sec_obj=None; cur_sub_obj=None; sec_idx=-1; prev_sub_num=None; pending_sec=None
            cc=canon_for(cur_theme)
            if cc: cur_theme_obj['theme']={"ru":cc['theme_ru'],"en":cc['theme_en']}
        elif t=='section':
            # Sections are inferred by subsection-number reset; the OCR section
            # title is only kept as a fallback for themes without a canonical.
            pending_sec={"ru":e.get('ru',''),"en":e.get('en','')}
        elif t=='sub':
            num=e.get('num',1)
            # new section on the first sub of a theme, or when numbering resets
            # (subsection numbers restart at 1 in each section of this book).
            if sec_idx==-1 or num==1 or (prev_sub_num is not None and num<=prev_sub_num):
                sec_idx+=1
                cc=canon_for(cur_theme)
                sec_canon=cc['sections'][sec_idx] if cc and sec_idx<len(cc['sections']) else None
                if sec_canon:
                    title={"ru":sec_canon['ru'],"en":sec_canon['en']}
                elif pending_sec:
                    title={"ru":pending_sec['ru'],"en":pending_sec['en']}
                else:
                    title={"ru":"","en":""}
                cur_sec_obj={"section":title,"subsections":[]}
                if cur_theme_obj is not None: cur_theme_obj['sections'].append(cur_sec_obj)
                pending_sec=None
            if cur_sec_obj is None:
                cur_sec_obj={"section":{"ru":pending_sec['ru'] if pending_sec else '',"en":pending_sec['en'] if pending_sec else ''},"subsections":[]}
                if cur_theme_obj is not None: cur_theme_obj['sections'].append(cur_sec_obj)
                pending_sec=None; sec_idx=0
            cc=canon_for(cur_theme)
            sub_canon=None
            if cc and sec_idx<len(cc['sections']):
                sub_canon=cc['sections'][sec_idx]['subs'].get(num)
            title={"ru":sub_canon['ru'],"en":sub_canon['en']} if sub_canon else {"ru":e.get('ru',''),"en":e.get('en','')}
            cur_sub_obj={"number":num,"subsection":title,"entries":[]}
            cur_sec_obj['subsections'].append(cur_sub_obj)
            prev_sub_num=num
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

    tree={"book":args.book,"themes":themes}
    json.dump(tree,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    ne=sum(len(ss['entries']) for th in themes for s in th['sections'] for ss in s['subsections'])
    ns=sum(len(th['sections']) for th in themes)
    nss=sum(len(s['subsections']) for th in themes for s in th['sections'])
    print(f"[build] themes={len(themes)} sections={ns} subsections={nss} entries={ne} -> {args.output}")

if __name__=='__main__':
    main()
