#!/usr/bin/env python3
"""Слияние двух словарей: 3000eng (base) + 3001eng.

Стратегия (обоснована диагностикой качества):
- Глаголы и Прилагательные берём из 3000eng как есть. 3000eng системно чище
  (ru/en без OCR-мусора), полнее по подразделам и записям. У 3001eng в этих темах
  ~267 «лишних» заглавных слов — это искажённые OCR-дубликаты того, что в 3000eng
  уже есть в чистом виде (станоннтьсн = становиться, нзбегать = избегать, …),
  поэтому их не добавляем.
- Существительные берём из 3001eng целиком: 3000eng содержит только раздел «Мир»
  (Небо, Земля, 15 записей), тогда как 3001eng содержит полную тему (21 раздел,
  90 подразделов, 1781 запись). Перекрытие (Небо/Земля) в обоих источниках
  идентично-чистое. Более чистого источника для названий разделов/подразделов
  существительных нет (canonical_nouns.json в 3001eng содержит те же строки).
- Транскрипцию (tran) не трогаем — пользователь просил не обращать внимания.
- `order` перенумеровывается сквозной по всем темам в порядке чтения.
"""
import argparse, copy, json, sys


# --- NOUN_FIX: точечные исправления OCR-шума в существительных ---
# Существительные импортируются из 3001eng целиком и несут остаточный OCR-мусор
# (мьщы→мышцы, мстро→метро, ииформация→информация и т.п. — внутрикириллические
# подмены, которые не ловит clean_en/fix_ru). Чистим воспроизводимо при импорте.
# Ключ — (page, исходная строка ru/en из 3001eng). Пополняй при новых ошибках.
NOUN_FIX_RU = {
    (123, "прямая лиия"): "прямая линия",
    (127, "метапл"): "металл",
    (127, "аюминий"): "алюминий",
    (129, "метаплолом"): "металлолом",
    (132, "зяяц"): "заяц",
    (133, "домашияя птица"): "домашняя птица",
    (133, "индюк' селезень"): "индюк селезень",
    (137, "мьщы"): "мышцы",
    (137, "ноготь покоть"): "ноготь локоть",
    (140, "удобства клюц"): "удобства ключ",
    (140, "кондиионер"): "кондиционер",
    (141, "одежный пкаф"): "одежный шкаф",
    (154, "нсобходимость"): "необходимость",
    (156, "ти"): "тип",
    (156, "принц"): "принцип",
    (156, "сообщенне"): "сообщение",
    (159, "учсбный год"): "учебный год",
    (163, "гардсроб"): "гардероб",
    (165, "гимнастнка"): "гимнастика",
    (165, "фугбол"): "футбол",
    (165, "бронзовая мёдаль"): "бронзовая медаль",
    (165, "нпчя"): "ничья",
    (169, "главпочтампт"): "главпочтамт",
    (174, "мстро"): "метро",
    (176, "ииформация"): "информация",
    (176, "свяятая ложь"): "святая ложь",
    (180, "наказанне"): "наказание",
    (181, "профсоюоз"): "профсоюз",
}
NOUN_FIX_EN = {
    (133, "lIamb foal"): "lamb foal",
    (136, "namne passport"): "name passport",
    (137, "abdomen chest neck back ebdoman"): "abdomen chest neck back",
    (141, "roOm"): "room",
    (143, "furcoat"): "fur coat",
    (144, "shoc polish"): "shoe polish",
    (147, "ma rinalade"): "marmalade",
    (148, "soured creamn"): "soured cream",
    (154, "rOOm"): "room",
    (156, "sucCess"): "success",
    (156, "exception sep"): "exception",
    (158, "mathematics lmagr"): "mathematics",
    (159, "jesson"): "lesson",
    (160, "phrase wOrd"): "phrase word",
    (161, "part of scntence"): "part of sentence",
    (165, "olympic games mprk"): "olympic games",
    (167, "transport communication comnerce"): "transport communication commerce",
    (167, "electric power plant paua"): "electric power plant",
    (168, "electronics engineer trunrks"): "electronics engineer",
    (169, "general post-office paust"): "general post-office",
    (171, "goods vanl"): "goods van",
    (171, "parts of the planc"): "parts of the plane",
    (173, "hom"): "horn",
    (176, "serrice centre"): "service centre",
    (176, "iie"): "lie",
    (179, "orthodox churcli"): "orthodox church",
    (180, "public prosccutor"): "public prosecutor",
    (181, "abolitiol constitution article adoption"):
        "abolition constitution article adoption",
    (182, "foreign tradc decrease"): "foreign trade decrease",
}
# Раздробленные OCR-записи: слить две строки в одну. (page, ru_keep, ru_drop, new_ru, new_en).
NOUN_MERGE = [
    (122, "защита окружающей", "среды ргэ",
     "защита окружающей среды", "environmental protection"),
]


def apply_noun_fix(theme_obj):
    """Применяет NOUN_FIX_RU/EN и слияния к импортированной теме существительных."""
    for s in theme_obj.get("sections", []):
        for ss in s.get("subsections", []):
            entries = ss.get("entries", [])
            for e in entries:
                k = (e.get("page"), e.get("ru"))
                if k in NOUN_FIX_RU:
                    e["ru"] = NOUN_FIX_RU[k]
                ke = (e.get("page"), e.get("en"))
                if ke in NOUN_FIX_EN:
                    e["en"] = NOUN_FIX_EN[ke]
            for page, ru_keep, ru_drop, new_ru, new_en in NOUN_MERGE:
                keep = next((e for e in entries
                             if e.get("page") == page and e.get("ru") == ru_keep), None)
                drop = next((e for e in entries
                             if e.get("page") == page and e.get("ru") == ru_drop), None)
                if keep and drop:
                    keep["ru"] = new_ru
                    keep["en"] = new_en
                    entries.remove(drop)
                    ss["entries"] = entries
    return theme_obj


def collect_entries(theme_obj):
    """Все записи темы в порядке чтения (плоско)."""
    out = []
    for s in theme_obj.get("sections", []):
        for ss in s.get("subsections", []):
            out.extend(ss.get("entries", []))
    return out


def renumber(dict_obj):
    n = 0
    for t in dict_obj["themes"]:
        for s in t.get("sections", []):
            for ss in s.get("subsections", []):
                for e in ss.get("entries", []):
                    n += 1
                    e["order"] = n
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="3000eng dictionary.json (чистый)")
    ap.add_argument("--other", required=True, help="3001eng dictionary.json (полные существительные)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    base = json.load(open(args.base, encoding="utf-8"))
    other = json.load(open(args.other, encoding="utf-8"))

    by_ru = {t["theme"]["ru"]: t for t in base["themes"]}
    by_ru_other = {t["theme"]["ru"]: t for t in other["themes"]}

    themes_order = ["Глаголы", "Прилагательные", "Существительные"]

    merged_themes = []
    report = []
    for name in themes_order:
        bt = by_ru.get(name)
        ot = by_ru_other.get(name)
        if name in ("Глаголы", "Прилагательные"):
            # base — авторитетный источник (чище, полнее).
            chosen = copy.deepcopy(bt)
            report.append(f"{name}: из base (3000eng) как есть; "
                          f"записей={len(collect_entries(chosen))}")
        elif name == "Существительные":
            # base почти пуст → берём полную тему из other (3001eng) и чистим OCR-шум.
            chosen = apply_noun_fix(copy.deepcopy(ot))
            n_other = len(collect_entries(ot)) if ot else 0
            n_base = len(collect_entries(bt)) if bt else 0
            report.append(f"{name}: из other (3001eng) целиком; "
                          f"записей {n_base}→{n_other} (+{n_other - n_base})")
        else:
            chosen = copy.deepcopy(bt or ot)
        merged_themes.append(chosen)

    out = {
        "book": base.get("book") or other.get("book"),
        "themes": merged_themes,
    }
    total = renumber(out)
    report.append(f"всего записей после слияния: {total}")

    json.dump(out, open(args.output, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n".join(report), file=sys.stderr)


if __name__ == "__main__":
    main()
