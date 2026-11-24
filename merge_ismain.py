#!/usr/bin/env python3
"""Допроставка is_main из 3001eng в уже смерженный dictionary.json.

Для Глаголов и Прилагательных: для каждой группы (страница, norm_ru), где в
3000eng НЕТ ни одного is_main=True, берём заголовок из 3001eng (если он там
отмечен) и ставим True на соответствующую запись в 3000eng. Это объединение
(union) — сохраняем проверенные заголовки 3000eng и добираем те, что поймал
только 3001eng (~79 групп). На эталонных стр.77-78 метрики совпадают, так что
доборы 3001eng считаем надёжными.

Существительные уже целиком из 3001eng — их is_main не трогаем.
Транскрипцию не трогаем.
"""
import argparse, json, re, sys


def norm(s):
    return re.sub(r'[^а-яёa-z]', '', (s or '').lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dict', required=True, help='смерженный dictionary.json')
    ap.add_argument('--other', required=True, help='3001eng dictionary.json')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    d = json.load(open(args.dict, encoding='utf-8'))
    o = json.load(open(args.other, encoding='utf-8'))

    # Для 3001eng: (theme, page, norm_ru) -> множество norm_en, отмеченных True
    other_true = {}
    for t in o['themes']:
        th = t['theme']['ru']
        for s in t.get('sections', []):
            for ss in s.get('subsections', []):
                for e in ss.get('entries', []):
                    if e.get('is_main'):
                        k = (th, e.get('page'), norm(e['ru']))
                        other_true.setdefault(k, set()).add(norm(e['en']))

    added = 0
    groups_touched = 0
    for t in d['themes']:
        th = t['theme']['ru']
        if th not in ('Глаголы', 'Прилагательные'):
            continue
        for s in t.get('sections', []):
            for ss in s.get('subsections', []):
                entries = ss.get('entries', [])
                # группируем записи по (page, norm_ru)
                groups = {}
                for e in entries:
                    k = (e.get('page'), norm(e['ru']))
                    groups.setdefault(k, []).append(e)
                for k, es in groups.items():
                    if any(e.get('is_main') for e in es):
                        continue  # в 3000eng уже есть заголовок
                    ok = other_true.get((th, k[0], k[1]))
                    if not ok:
                        continue  # 3001eng тоже не отметил — синоним без заголовка
                    # ищем запись в группе с совпадающим norm_en
                    target = next((e for e in es if norm(e['en']) in ok), None)
                    if target is None:
                        target = es[0]  # fallback: первая запись группы (обычно голова)
                    if not target.get('is_main'):
                        target['is_main'] = True
                        added += 1
                        groups_touched += 1

    json.dump(d, open(args.output, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'добавлено is_main=True: {added} (по {groups_touched} группам)',
          file=sys.stderr)


if __name__ == '__main__':
    main()
