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
        'go On':'go on','g0 On':'go on',
        # Systematic easyocr confusions on these photos (c↔e, i↔l/t, rn↔m, cl↔d,
        # n↔ion, l↔i). Each is an unresolved token that becomes a CMUdict word after
        # the fix, so the IPA pass can transcribe it. Only distinctive garbles that
        # cannot be a substring of a real English word are safe as a global replace;
        # ambiguous ones (e.g. 'iate'→late, which bites 'appreciate') are handled as
        # per-entry OVERRIDES in merge_dicts.py instead.
        'bugin':'begin','becomc':'become','continuc':'continue','dclay':'delay',
        'postponc':'postpone','resuline':'resume','fmish':'finish','breuk':'break',
        'intcrrupt':'interrupt','slon':'slow','slidc':'slide','rotatc':'rotate',
        'skatc':'skate','nursc':'nurse','suipass':'surpass','escane':'escape',
        'stalt':'start','mleet':'meet','drowmn':'drown','cnter':'enter','hclong':'belong',
        'icquire':'acquire','cmpty':'empty','ahsemt':'absent','rescarch':'research',
        'timctable':'timetable','eoat':'coat','hlood':'blood','hcad':'head',
        'objcction':'objection','subjcct':'subject','shakc':'shake','iift':'lift',
        'iazy':'lazy','brcak':'break','inla':'into','iast':'last','spea':'speak',
        'shup':'ship','suflicicnt':'sufficient','CKist':'exist','ihere':'there',
        'kros':'cross','CTOSS':'cross','comeacross':'come across','cven':'even',
        'surlacc':'surface','freh':'fresh','slau':'slow','thc':'the',
        # 3001eng photo set: systematic en-token garbles → CMUdict words.
        'appcar':'appear','tesue':'resume','ceasc':'cease','mheet':'meet','CIOsS':'cross',
        'cxist':'exist','mnarry':'marry','cconomize':'economize','awakc':'awake',
        'hcal':'heal','speakk':'speak','imvite':'invite','letive':'leave','botler':'bother',
        'offcnd':'offend','invacle':'invade','submnit':'submit','lIittle':'little',
        'nedr':'near','rectangulat':'rectangular','odourlcss':'odourless','sliolt':'short',
        'modelm':'modern','giftcd':'gifted','txtlented':'talented','nervots':'nervous',
        'handsomne':'handsome','tepulsive':'repulsive','excitcd':'excited','grcedy':'greedy',
        'variouls':'various','simnilar':'similar','iawful':'lawful','advantagcous':'advantageous',
        'hcalthy':'healthy','slimn':'slim','mnoon':'moon','inouth':'mouth','summiit':'summit',
        'autzu':'autumn','SIOw':'snow','sccond':'second','paimt':'paint','petroleumn':'petroleum',
        'tomnato':'tomato','iemon':'lemon','crownl':'crown','jion':'lion','stalfion':'stallion',
        'madamn':'madam','dinig-room':'dining-room','fomm':'form','cquipment':'equipment',
        'repcrtoire':'repertoire','vollcyball':'volleyball','speakr':'spear','tumer':'turner',
        'mnanager':'manager','ervelope':'envelope','iuggage':'luggage','lleWs':'news',
        'rcception':'reception','gulest':'guest','nlation':'nation','smnoking':'smoking',
        'ointmnent':'ointment','doughut':'doughnut','specch':'speech','hdrance':'advance'}
def fix_en(s):
    for k,v in EN_FIX.items(): s=s.replace(k,v)
    return re.sub(r'\s+',' ',s).strip(' ;:,.\'"')

def clean_en(s):
    """Drop residual OCR-noise fragments from an English translation and normalize
    case. Noise = tokens carrying digits, bare single letters, mixed-case 2-letter
    blobs, or stray symbols; real translations are lowercase alphabetic words
    (optionally with -/'). Title-case words (e.g. OCR "Size") are lowercased.
    Parenthesized words — "(into)", "(along)", "(left)", "(with)", "(+adj)" —
    are preserved (only the core inside the parens is noise-checked)."""
    out=[]
    for tok in s.split():
        core=tok.strip(" ;:,.\"'`()+")   # strip parens/+ for the noise check
        if not core: continue
        if re.search(r'\d', core): continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]?|[A-Za-z]", core): continue
        if len(core)==1 and core not in ('a','I','O'): continue
        if len(core)==2 and core[0].isupper() and core[1].islower(): continue
        keep=tok.strip(" ;:,.\"'`")      # keep parentheses/+ in the output
        if len(core)>=2 and core[0].isupper() and core[1:].islower() and core.isalpha():
            keep=keep.lower()
        out.append(keep)
    return re.sub(r'\s+',' ', ' '.join(out)).strip(' ;:,.\'"')

def fix_ru(s):
    s=re.sub(r'^\d+\s*','',s)                 # leading stray digit
    s=re.sub(r'\s+\d+(?:\s+\d+)*\s*$','',s)   # trailing stray digits
    # OCR often bundles the bracketed transcription into the ru column
    # ("стирать [wdл", "толкать [puл"); cut from the first '[' — no real ru
    # headword contains a bracket.
    s=re.sub(r'\[.*$','',s)
    s=s.replace('0','о')                       # '0' is OCR noise for Cyrillic 'о'
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
    ap.add_argument('--canonical', action='append', default=[],
                   help='clean-titles overlay (per-theme); repeat once per theme')
    ap.add_argument('--book', default='Словарь-минимум с логической структурой')
    args=ap.parse_args()

    events=json.load(open(args.input,encoding="utf-8"))
    canons=[load_canonical(p) for p in args.canonical] if args.canonical else []
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

    BOLD_RATIO=1.14   # stroke/max(ru,en) divided by page-median ru stroke → bold
    # Tuned for this photo set (3001eng): the bold/regular stroke separation is
    # narrower than the 1.30 calibrated on the earlier scan, so on p77–78 the
    # эталон bold words (start, grow, continue, put off, repeat, finish, break,
    # cease …) sit at ratio 1.14–1.28 while regular text is ≤1.08. 1.14 recovers
    # 10/10 of the verified эталон with no false positives on those pages.

    themes=[]; cur_theme=None; cur_theme_obj=None
    cur_sec_obj=None; cur_sub_obj=None; order=0
    sec_idx=-1; prev_sub_num=None
    pending_sec=None     # most recent centered section title from OCR (fallback)

    def canon_for(theme_ru):
        if not canons: return None
        for c in canons:
            if c['theme_ru'] is None: return c            # back-compat (no theme)
            if c['theme_ru']==theme_ru: return c
        return None

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
            ru=fix_ru(e.get('ru','')); en=clean_en(fix_en(e.get('en',''))); tr=e.get('tr','')
            if not ru and not en: continue
            st=e.get('stroke'); med=page_med.get(e.get('page'))
            ratio=(st/med) if (st and med) else None
            # is_main: the bold "главное слово группы". Boldness is measured on the
            # pixels of BOTH the Russian and the English word (transcription is never
            # bold), as the thickest stroke width normalized per page.
            is_main = ratio is not None and ratio>=BOLD_RATIO
            entry={"order":order,"page":e.get('page'),"ru":ru,"en":en,
                   "tran":tr,"is_main":bool(is_main)}
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
