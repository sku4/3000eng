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
    # === Глаголы: ru OCR-noise + empty/garbled en recovery (en inferred from the
    # book's printed transcription where OCR dropped it) ===
    {"page":77,"ru":"поянляться","set_ru":"появляться"},
    {"page":78,"ru":"продолжать","set_ru":"продолжать","set_en":"go on"},
    {"page":78,"ru":"завершять(ся)","set_ru":"завершать(ся)"},
    {"page":78,"ru":"прерынать","set_ru":"прерывать"},
    {"page":78,"ru":"двигать(ся) останавлнвать(ся) mlоке","set_ru":"двигать(ся)","set_en":"move"},
    {"page":79,"ru":"катить(ся)","set_en":"roll"},
    {"page":79,"ru":"поворачивать(ся) tuiп","set_ru":"поворачивать(ся)","set_en":"turn"},
    {"page":79,"ru":"опускать роwег","set_ru":"опускать","set_en":"lower"},
    {"page":79,"ru":"бежать iп","set_ru":"бежать","set_en":"run"},
    {"page":79,"ru":"idлзтh сгеер","set_ru":"ползти","set_en":"creep"},
    {"page":80,"ru":"убежать еscape","set_ru":"убежать","set_en":"escape"},
    {"page":80,"ru":"продвигяться","set_ru":"продвигаться","set_en":"advance"},
    {"page":80,"ru":"врезаться (в) ruп (into)","set_ru":"врезаться (в)","set_en":"run (into)"},
    {"page":80,"ru":"прибывать яrrive","set_ru":"прибывать","set_en":"arrive"},
    {"page":81,"ru":"грести rон","set_ru":"грести","set_en":"row"},
    {"page":83,"ru":"оставатьсн remaiп","set_ru":"оставаться","set_en":"remain"},
    {"page":83,"ru":"лажнтьн iie dоwn","set_ru":"ложиться","set_en":"lie down"},
    {"page":84,"ru":"рождать hеaг","set_ru":"рождать","set_en":"bear"},
    {"page":84,"ru":"назынать iamе","set_ru":"называть","set_en":"name"},
    {"page":84,"ru":"женнться","set_ru":"жениться"},
    {"page":84,"ru":"ряботать","set_ru":"работать","set_en":"work"},
    {"page":84,"ru":"зарабатывать снгп","set_ru":"зарабатывать","set_en":"earn"},
    {"page":84,"ru":"патить раy","set_ru":"платить","set_en":"pay"},
    {"page":85,"ru":"заказыннть","set_ru":"заказывать","set_en":"order"},
    {"page":90,"ru":"знать","set_en":"know"},
    {"page":86,"ru":"выздоравливать rесотeг","set_ru":"выздоравливать","set_en":"recover"},
    {"page":88,"ru":"полагаться relу","set_ru":"полагаться","set_en":"rely"},
    {"page":89,"ru":"слышать","set_en":"hear"},
    {"page":92,"ru":"ремонтировать reрair","set_ru":"ремонтировать","set_en":"repair"},
    {"page":92,"ru":"проверять","set_en":"control"},
    {"page":95,"ru":"отвечать rерlу","set_ru":"отвечать","set_en":"reply"},
    {"page":97,"ru":"уходить (из гостей)","set_en":"leave"},
    # === Глаголы: p82 dense-region merged rows (split via INSERTS below) ===
    {"page":82,"ru":"бытъ достаточным lbr sэ' frjэnt]","set_ru":"быть достаточным"},
    {"page":82,"ru":"принадлежять","set_ru":"принадлежать"},
    {"page":82,"ru":"нключать","set_ru":"включать"},
    {"page":82,"ru":"требовать","set_en":"require"},
    {"page":82,"ru":"быть необходнмым","set_ru":"быть необходимым"},
    {"page":82,"ru":"опорожнятъ отсутствовать не хватять","set_ru":"опорожнять","set_en":"empty"},
    {"page":82,"ru":"быть пустым","set_ru":"быть пустым"},
    {"page":82,"ru":"быть полным иаполннть","set_ru":"быть полным","set_en":"be full"},
    {"page":82,"ru":"накаппинать","set_ru":"накапливать"},
    {"page":82,"ru":"быть н избытке","set_ru":"быть в избытке"},
    # === Прилагательные ===
    {"page":100,"ru":"непрозрачный ораque","set_ru":"непрозрачный","set_en":"opaque"},
    {"page":101,"ru":"близкий","set_en":"near"},
    {"page":102,"ru":"прохладный","set_en":"cool"},
    {"page":104,"ru":"поздй","set_ru":"поздний","set_en":"late"},
    {"page":105,"ru":"случайный","set_en":"occasional"},
    {"page":105,"ru":"одарепный","set_ru":"одарённый"},
    {"page":105,"ru":"талатливый","set_ru":"талантливый"},
    {"page":106,"ru":"ленивый","set_en":"lazy"},
    {"page":106,"ru":"внимательный","set_en":"careful"},
    {"page":107,"ru":"счастливый hарру","set_ru":"счастливый","set_en":"happy"},
    {"page":108,"ru":"горестный","set_en":"sorrowful"},
    {"page":108,"ru":"чудесный","set_en":"wonderful"},
    {"page":108,"ru":"удивителыый","set_ru":"удивительный"},
    {"page":108,"ru":"трогателыый","set_ru":"трогательный"},
    {"page":108,"ru":"страшньй","set_ru":"странный"},
    {"page":108,"ru":"приятш","set_ru":"приятный"},
    {"page":108,"ru":"отличный","set_ru":"отличный"},
    {"page":109,"ru":"страшный","set_en":"fearful"},
    {"page":109,"ru":"взволююванный","set_ru":"взволнованный"},
    {"page":111,"ru":"жадны","set_ru":"жадный"},
    {"page":115,"ru":"законньй","set_ru":"законный","set_en":"lawful"},
    {"page":116,"ru":"стройныйй","set_ru":"стройный"},
    # === Существительные ===
    {"page":118,"ru":"суша","set_en":"land"},
    {"page":121,"ru":"ией","set_ru":"иней"},
    {"page":119,"ru":"устье","set_en":"mouth"},
    {"page":123,"ru_contains":"площадь","set_ru":"площадь","set_en":"area"},
    {"page":127,"ru":"медь сopper","set_ru":"медь","set_en":"copper"},
    {"page":130,"ru":"лимон","set_en":"lemon"},
    {"page":131,"ru":"акация acaсiа","set_ru":"акация","set_en":"acacia"},
    {"page":131,"ru":"крона","set_en":"crown"},
    {"page":132,"ru":"подснсжник","set_ru":"подснежник"},
    {"page":132,"ru":"лев","set_en":"lion"},
    {"page":133,"ru":"курица hеn","set_ru":"курица","set_en":"hen"},
    {"page":134,"ru":"карп саrр","set_ru":"карп","set_en":"carp"},
    {"page":136,"ru":"господин (перед именем","set_ru":"господин (перед именем)","set_en":"mister"},
    {"page":136,"ru":"обращение перед именем","set_en":"mrs; ms"},
    {"page":138,"ru":"ухо еаг","set_ru":"ухо","set_en":"ear"},
    {"page":139,"ru":"зять sоn-in-iaw","set_ru":"зять","set_en":"son-in-law"},
    {"page":140,"ru":"крыша roоf","set_ru":"крыша","set_en":"roof"},
    {"page":144,"ru":"шапка фуражка / кепка cар","set_ru":"шапка фуражка / кепка","set_en":"cap"},
    {"page":148,"ru":"овсяная круп","set_ru":"овсяная крупа","set_en":"oatmeal"},
    {"page":149,"ru":"пирожок пончк","set_ru":"пирожок пончик"},
    {"page":151,"ru":"злоба преступное намерение malice","set_ru":"злоба преступное намерение","set_en":"malice"},
    {"page":152,"ru":"наглость impjudэns]","set_ru":"наглость"},
    {"page":152,"ru":"пь","set_ru":"пыл","set_en":"ardour"},
    {"page":155,"ru":"оборудованис","set_ru":"оборудование"},
    {"page":159,"ru":"класс уеаг","set_ru":"класс","set_en":"year"},
    {"page":160,"ru":"речь","set_ru":"речь"},
    {"page":163,"ru":"программа","set_en":"programme"},
    {"page":165,"ru":"баскетбол","set_en":"basketball"},
    {"page":165,"ru":"финал","set_en":"final"},
    {"page":165,"ru":"медаль","set_en":"medal"},
    {"page":167,"ru":"машиностроительный завод engineering works","set_ru":"машиностроительный завод","set_en":"engineering works"},
    {"page":175,"ru":"зоопарк","tr_contains":"zu","set_en":"zoo"},
    {"page":171,"ru":"багаж","set_en":"luggage"},
    {"page":185,"ru":"pelтreн x-rау","set_ru":"рентген","set_en":"x-ray"},
    # === ru cleanup: transcription/English glued into the ru column + cyrillic
    # letter misreads (en already clean). fix_ru strips leading '[' debris; these
    # are the residual tails / mid-word latin / orphan transcription fragments. ===
    {"page":79,"ru":"кататься ha лыжах","set_ru":"кататься на лыжах"},
    {"page":80,"ru":"нстречаться а'krds]","set_ru":"встречаться","set_en":"come across"},
    {"page":81,"ru":"плявать течь поw","set_ru":"плавать"},
    {"page":84,"ru":"родитъся bэ:n]","set_ru":"рождаться"},
    {"page":86,"ru":"вытираться причесываться hеа]","set_ru":"вытираться причесываться",
     "set_en":"dry comb one's hair oneself"},
    {"page":86,"ru":"делать прическу waпz","set_ru":"делать прическу"},
    {"page":88,"ru":"зазнаваться еэz]","set_ru":"зазнаваться"},
    {"page":88,"ru":"быть наглым insэlэnt]","set_ru":"быть наглым"},
    {"page":88,"ru":"уставать, быть уставшим taтэd]","set_ru":"уставать, быть уставшим"},
    {"page":92,"ru":"ронять fэ:]","set_ru":"ронять"},
    {"page":92,"ru":"поднять (c пола)","set_ru":"поднять (с пола)"},
    {"page":93,"ru":"убрать, отложить э'wei]","set_ru":"убрать, отложить"},
    {"page":96,"ru":"давать ha время","set_ru":"давать на время"},
    {"page":97,"ru":"прощцаться baт]","set_ru":"прощаться","set_en":"say goodbye"},
    {"page":105,"ru":"нечастый fri:kwэг1]","set_ru":"нечастый"},
    {"page":107,"ru":"несчастливый hтpт]","set_ru":"несчастливый"},
    {"page":113,"ru":"важный im'рэ:(э)nt]","set_ru":"важный"},
    {"page":113,"ru":"уступающий f1(э)гхэ]","set_ru":"уступающий"},
    {"page":122,"ru":"разрушение rjэn]","set_ru":"разрушение"},
    {"page":122,"ru":"единица измерения эv","set_ru":"единица измерения"},
    {"page":127,"ru":"чугун атэn]","set_ru":"чугун"},
    {"page":127,"ru":"mэ't1эrтlz]","set_ru":"материалы"},
    {"page":129,"ru":"teтjэn]","set_ru":"плантация","set_en":"plantation"},
    {"page":138,"ru":"нoc","set_ru":"нос"},
    {"page":138,"ru":"лоб fэ hed]","set_ru":"лоб"},
    {"page":139,"ru":"невестка э:]","set_ru":"невестка"},
    {"page":139,"ru":"хозяин ma:stэ]","set_ru":"хозяин"},
    {"page":140,"ru":"оkiо","set_ru":"окно"},
    {"page":147,"ru":"минеральная вода wэ:ta]","set_ru":"минеральная вода"},
    {"page":152,"ru":"нетерпимость in' tol(э )rэns]","set_ru":"нетерпимость"},
    {"page":152,"ru":"хорошие манеры manэz]","set_ru":"хорошие манеры"},
    {"page":152,"ru":"стремление lespi'rer (э)n]","set_ru":"стремление"},
    {"page":155,"ru":"показания indr'kеr (э)n]","set_ru":"показания"},
    {"page":155,"ru":"открытие изменение mddrf-'ker (э )n]","set_ru":"открытие изменение"},
    {"page":158,"ru":"университет lju:ni'vз:sit-]","set_ru":"университет"},
    {"page":161,"ru":"действительный залог vэis]","set_ru":"действительный залог"},
    {"page":161,"ru":"страдательный залог vэis]","set_ru":"страдательный залог"},
    {"page":162,"ru":"антракт intэv(э)l]","set_ru":"антракт"},
    {"page":166,"ru":"безработица кnim plэimэnt]","set_ru":"безработица"},
    {"page":167,"ru":"автозавод wз:ks]","set_ru":"автозавод"},
    {"page":167,"ru":"нефтеперегонный завод rr'faт(э)гэ]","set_ru":"нефтеперегонный завод"},
    {"page":168,"ru":"занятие dkju'pe л(э)n]","set_ru":"занятие"},
    {"page":169,"ru":"аппарат ерэ' reitэs]","set_ru":"аппарат"},
    {"page":170,"ru":"международный разговор intэ' naj(э)nэl","set_ru":"международный разговор"},
    {"page":170,"ru":"жслезнодорожпая станция / steтjn]","set_ru":"железнодорожная станция"},
    {"page":171,"ru":"xbост шасси","set_ru":"хвост шасси"},
    {"page":172,"ru":"endsin1э]","set_ru":"инженер"},
    {"page":175,"ru":"универмаг stэ:]","set_ru":"универмаг"},
    {"page":178,"ru":"гиh","set_ru":"гимн"},
    {"page":179,"ru":"люди население народ popju'le (э)n]","set_ru":"население народ"},
    {"page":181,"ru":"принятие конституция статья отмена (э)n]","set_ru":"принятие конституция статья отмена"},
    {"page":182,"ru":"интервенция inta' ven (э )n]","set_ru":"интервенция"},
    {"page":183,"ru":"профилактика заболеваний preventive measures здоровье гигиена meзэz]",
     "set_ru":"профилактика заболеваний здоровье гигиена","set_en":"preventive measures health hygiene"},
    {"page":183,"ru":"употреблснис спиртного вред для здоровья hezэd]",
     "set_ru":"употребление спиртного вред для здоровья"},
]
INSERTS=[
    # p82: split the merged dense-region rows into their real entries
    {"page":82,"after_ru":"опорожнять","ru":"отсутствовать","en":"be absent"},
    {"page":82,"after_ru":"отсутствовать","ru":"не хватать","en":"lack"},
    {"page":82,"after_ru":"быть полным","ru":"наполнить","en":"fill"},
]
DELETES=[
    {"page":186,"ru_contains":"тебе"},    # pronoun junk from the back-cover row of p186
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

    # Drop subsections/sections left empty after corrections (e.g. the trailing
    # back-cover garbage section on p186 once its junk entry is deleted).
    for th in themes:
        for s in th['sections']:
            s['subsections']=[ss for ss in s['subsections'] if ss['entries']]
        th['sections']=[s for s in th['sections'] if s['subsections']]

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
