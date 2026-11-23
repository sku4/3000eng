#!/usr/bin/env python3
"""Merge several dictionary files into one (new multi-theme schema).

Each input may be either:
  - old schema: {"book","theme":{ru,en},"sections":[...]}
  - new schema: {"book","themes":[{theme, sections}]}

All themes from all inputs are concatenated in input order, OCR noise is
stripped from `en` (clean_en, preserving parenthesized words), then a manual
CORRECTIONS map is applied (overrides / inserts / deletes) to fix row-shifted
translations and field garbage that automatic parsing could not recover.
Finally the entries' `order` is renumbered contiguously across the whole result.

Usage:
    python merge_dicts.py --inputs dictionary_verbs.json adj_dict.json --output dictionary.json
"""
import argparse, json
from build_json import clean_en
from ipa import transcribe

def to_themes(d):
    if 'themes' in d:
        return d['themes']
    return [{"theme":d['theme'],"sections":d['sections']}]

# --- Manual corrections for OCR row-shifts and field garbage -------------------
# Each entry is matched by (page, exact ru), optionally disambiguated by
# en_contains / tr_contains (substrings of the current en / transcription).
# Overrides set only the fields listed (set_ru / set_en / set_tr).
# Inserts add a new entry right after the matched anchor. Deletes remove it.
OVERRIDES=[
    # === Глаголы: p82 cascade (en column shifted one row up) ===
    {"page":82,"ru":"достаточном кол-ве","set_ru":"иметь в достаточном кол-ве"},
    {"page":82,"ru":"быть","set_en":"be","set_tr":"[bi:]"},
    {"page":82,"ru":"принадлежать","set_en":"belong","set_tr":"[br'lon]"},
    {"page":82,"ru":"содержать","set_en":"contain","set_tr":"[kэn'temn]"},
    {"page":82,"ru":"включать","set_en":"include","set_tr":"[In'klu:d]"},
    {"page":82,"ru":"требовать","set_en":"demand","set_tr":"[dr'ma:nd]"},
    {"page":82,"ru":"быть необходимым","set_en":"be necessary","set_tr":"[br' nesIs(э)rI]"},
    {"page":82,"ru":"не хватать","set_en":"lack","set_tr":"[Iek]"},
    {"page":82,"ru":"отсутствовать","set_en":"be absent","set_tr":"[br 'ebsent]"},
    {"page":82,"ru":"опорожнять","set_en":"empty","set_tr":"[emptr]"},
    # === Глаголы: other field garbage / fragments ===
    {"page":81,"ru":"имсть","set_ru":"иметь"},
    {"page":86,"ru":"чистить","en_contains":"comb","set_en":"clean","set_tr":"[kli:n]"},
    {"page":86,"ru":"причесываться","set_en":"comb one's hair","set_tr":"[koum WAnZ 'heэ]"},
    {"page":90,"ru":"помнит","set_ru":"помнить"},
    {"page":88,"ru":"стараться сделать все","set_ru":"стараться сделать все возможное",
     "set_en":"try to do one's best","set_tr":"[trar tэ 'du: WAIZ best]"},
    {"page":89,"ru":"удивлять amaze паwf","set_ru":"удивлять","set_en":"amaze","set_tr":"[э'merz]"},
    {"page":89,"ru":"баньсердитым","set_ru":"быть сердитым","set_en":"be angry","set_tr":"[br 'engri]"},
    {"page":87,"ru":"обожать llijt4ъ","set_ru":"обожать"},
    {"page":89,"ru":"оскорблять .х <","set_ru":"оскорблять"},
    {"page":93,"ru":"завязывать; привязывать","set_en":"tie","set_tr":"[taI]"},
    {"page":93,"ru":"открывать ;м #","set_ru":"открывать"},
    {"page":97,"ru":"знакомиться","en_contains":"acquaintance","set_en":"make acquaintance",
     "set_tr":"[merk э'kweIntэns]"},
    {"page":97,"ru":"быть знакомым","set_tr":"[bI э'kweintid]"},
    # === Прилагательные ===
    {"page":101,"ru":"большой","en_contains":"nicu","set_en":"big"},
    {"page":104,"ru":"новейший lxp tэ' dert]","set_ru":"новейший","set_tr":"[Ap tu:'dert]"},
    {"page":107,"ru":"счастливый hapру","set_ru":"счастливый","set_en":"happy","set_tr":"[hapi]"},
    # p108 synonym-group cascade (en one row up)
    {"page":108,"ru":"хорошем настроении","set_ru":"в хорошем настроении",
     "set_en":"high-spirited","set_tr":"[harsprritid]"},
    {"page":108,"ru":"оптимистический","set_en":"optimistic","set_tr":"[opti mIstik]"},
    {"page":108,"ru":"печальный","set_en":"sad","set_tr":"[sed]"},
    {"page":108,"ru":"пессимистический в плохом настроении","set_ru":"пессимистический",
     "set_en":"pessimistic","set_tr":"[pesi mIstrk]"},
    {"page":108,"ru":"удивительный [sэ","set_ru":"удивительный","set_en":"surprising",
     "set_tr":"[sэ'praIzIn]"},
    {"page":109,"ru":"сердитый","en_contains":"CrOsS","set_en":"cross","set_tr":"[kros]"},
    {"page":109,"ru":"оскорбленный 311й","set_ru":"оскорбленный"},
    {"page":110,"ru":"эгоистичный [selfiл","set_ru":"эгоистичный","set_en":"selfish","set_tr":"['selfiЛ]"},
    {"page":110,"ru":"послушный [э bi:diэnt]","set_ru":"послушный","set_en":"obedient",
     "set_tr":"[э'bi:diэnt]"},
    {"page":111,"ru":"непослушный art","set_ru":"непослушный"},
    {"page":112,"ru":"высокомерный","en_contains":"light-minded","set_en":"light-minded",
     "set_tr":"[lart mamndid]"},
    {"page":113,"ru":"главный осt","set_ru":"главный"},
    {"page":113,"ru":"различный } |","set_ru":"различный"},
    {"page":113,"ru":"важный","en_contains":"ixrro","set_en":"important"},
    {"page":113,"ru":"искусственный la:tr'f1/(э)l]","set_ru":"искусственный","set_en":"artificial",
     "set_tr":"[a:tr'f1Л(э)l]"},
    {"page":114,"ru":"недостаточный [insэ frj(э)nt]","set_ru":"недостаточный","set_en":"insufficient",
     "set_tr":"[Insэ'frJэnt]"},
    {"page":115,"ru_contains":"неуместный [aut","en_contains":"out of place","set_ru":"неуместный",
     "set_en":"out of place","set_tr":"[aut эv pleIs]"},
    {"page":116,"ru":"недействительный эзивы1о: invalid","set_ru":"недействительный",
     "set_en":"invalid","set_tr":"[In'velId]"},
    {"page":116,"ru":"богатый [ritл","set_ru":"богатый","set_en":"rich","set_tr":"[rItЛ]"},
    {"page":117,"ru":"свободный","tr_contains":"verkont","set_ru":"свободный, вакантный",
     "set_en":"vacant","set_tr":"[verkont]"},
    # === en recovery: translations lost / garbled beyond clean_en (needed so IPA
    # can be generated from a correct English headword) ===
    {"page":88,"ru":"лениться","set_en":"be lazy"},                 # OCR "be jazy"
    {"page":95,"ru":"предупреждать","set_en":"warn"},               # OCR "wam"
    {"page":115,"ru":"невыгодный","set_en":"disadvantageous"},      # OCR garbage
    {"page":106,"ru":"внимательный","tr_contains":"еэf","set_en":"careful"},   # en was empty
    {"page":114,"ru":"условный","tr_contains":"kэn","set_en":"conditional"},   # en was empty
]
INSERTS=[
    {"page":108,"after_ru":"печальный","ru":"огорченный","en":"sorry","tr":"[sorI]"},
    {"page":108,"after_ru":"пессимистический","ru":"в плохом настроении","en":"low-spirited",
     "tr":"[lэu'spirItrd]"},
]
DELETES=[
    {"page":82,"ru":"иметь b"},          # fragment of «быть»
    {"page":82,"ru":"достаточным"},       # fragment
    {"page":89,"ru":"быть"},              # merged into «быть сердитым»
    {"page":88,"ru":"возможное"},         # merged into «стараться сделать все возможное»
    {"page":117,"ru":"вакантный"},        # merged into «свободный, вакантный»
]

def _match(entry, page, ru=None, ru_contains=None, en_contains=None, tr_contains=None):
    if entry.get('page')!=page:
        return False
    if ru is not None and entry.get('ru')!=ru:
        return False
    if ru_contains is not None and ru_contains not in entry.get('ru',''):
        return False
    if en_contains is not None and en_contains not in entry.get('en',''):
        return False
    if tr_contains is not None and tr_contains not in entry.get('tran',''):
        return False
    return True

def apply_corrections(themes):
    # flatten entries with parent (subsection) for insert/delete
    def all_pairs():
        for th in themes:
            for s in th['sections']:
                for ss in s['subsections']:
                    for e in ss['entries']:
                        yield th,s,ss,e
    # 1) overrides
    for spec in OVERRIDES:
        hits=[(ss,e) for th,s,ss,e in all_pairs()
              if _match(e, spec['page'], spec.get('ru'), spec.get('ru_contains'),
                        spec.get('en_contains'), spec.get('tr_contains'))]
        if len(hits)!=1:
            print(f"  [corr] OVERRIDE {spec['page']}/{spec.get('ru') or spec.get('ru_contains')!r}: matched {len(hits)} (expected 1) — SKIPPED")
            continue
        ss,e=hits[0]
        if 'set_ru' in spec: e['ru']=spec['set_ru']
        if 'set_en' in spec: e['en']=spec['set_en']
        if 'set_tr' in spec: e['tran']=spec['set_tr']
    # 2) deletes
    for spec in DELETES:
        for th in themes:
            for s in th['sections']:
                for ss in s['subsections']:
                    ss['entries']=[e for e in ss['entries']
                                   if not _match(e, spec['page'], spec.get('ru'), spec.get('ru_contains'),
                                                 spec.get('en_contains'), spec.get('tr_contains'))]
    # 3) inserts (after anchor matched by page+ru)
    for spec in INSERTS:
        done=False
        for th in themes:
            if done: break
            for s in th['sections']:
                if done: break
                for ss in s['subsections']:
                    if done: break
                    for i,e in enumerate(ss['entries']):
                        if e.get('page')==spec['page'] and e.get('ru')==spec['after_ru']:
                            new={"order":-1,"page":spec['page'],"ru":spec['ru'],
                                 "en":spec['en'],"tran":spec.get('tr',''),"is_main":False}
                            ss['entries'].insert(i+1,new)
                            done=True
                            break
        if not done:
            print(f"  [corr] INSERT anchor {spec['page']}/{spec['after_ru']!r} not found — SKIPPED")

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

    # strip OCR noise + drop service fields + normalize key transcription -> tran
    for th in themes:
        for s in th['sections']:
            for ss in s['subsections']:
                ss.pop('subsection_ocr', None)
                for e in ss['entries']:
                    e['en']=clean_en(e.get('en',''))
                    if 'transcription' in e:
                        if 'tran' not in e: e['tran']=e.pop('transcription')
                        else: e.pop('transcription')

    apply_corrections(themes)

    # Replace every OCR-mangled transcription with a correct IPA transcription
    # generated from the (now cleaned / corrected) English headword via CMUdict
    # (British non-rhotic RP — see ipa.py). Entries whose en still can't be
    # resolved keep their OCR transcription as a fallback.
    for th in themes:
        for s in th['sections']:
            for ss in s['subsections']:
                for e in ss['entries']:
                    ipa=transcribe(e.get('en',''))
                    if ipa:
                        e['tran']=ipa

    # renumber order contiguously
    order=0
    for th in themes:
        for s in th['sections']:
            for ss in s['subsections']:
                for e in ss['entries']:
                    e['order']=order; order+=1

    tree={"book":args.book,"themes":themes}
    json.dump(tree,open(args.output,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    ne=sum(len(ss['entries']) for th in themes for s in th['sections'] for ss in s['subsections'])
    print(f"[merge] themes={len(themes)} sections={sum(len(th['sections']) for th in themes)} "
          f"subs={sum(len(s['subsections']) for th in themes for s in th['sections'])} entries={ne} -> {args.output}")

if __name__=='__main__':
    main()
