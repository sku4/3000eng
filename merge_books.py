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
            # base почти пуст → берём полную тему из other (3001eng).
            chosen = copy.deepcopy(ot)
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
