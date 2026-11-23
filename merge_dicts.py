#!/usr/bin/env python3
"""Merge several dictionary files into one (new multi-theme schema).

Each input may be either:
  - old schema: {"book","theme":{ru,en},"sections":[...]}
  - new schema: {"book","themes":[{theme, sections}]}

All themes from all inputs are concatenated in input order and the entries'
`order` field is renumbered contiguously across the whole result.

Usage:
    python merge_dicts.py --inputs dictionary_verbs.json adj_dict.json --output dictionary.json
"""
import argparse, json

def to_themes(d):
    if 'themes' in d:
        return d['themes']
    return [{"theme":d['theme'],"sections":d['sections']}]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--inputs', nargs='+', required=True)
    ap.add_argument('--output', default='dictionary.json')
    ap.add_argument('--book', default='Словарь-минимум с логической структурой')
    args=ap.parse_args()

    themes=[]
    for path in args.inputs:
        d=json.load(open(path,encoding="utf-8"))
        themes.extend(to_themes(d))

    order=0
    for th in themes:
        for s in th['sections']:
            for ss in s['subsections']:
                ss.pop('subsection_ocr', None)   # service field, not in final dict
                for e in ss['entries']:
                    e['order']=order; order+=1

    tree={"book":args.book,"themes":themes}
    json.dump(tree,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    ne=sum(len(ss['entries']) for th in themes for s in th['sections'] for ss in s['subsections'])
    print(f"[merge] themes={len(themes)} sections={sum(len(th['sections']) for th in themes)} "
          f"subs={sum(len(s['subsections']) for th in themes for s in th['sections'])} entries={ne} -> {args.output}")

if __name__=='__main__':
    main()
