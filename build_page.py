#!/usr/bin/env python3
"""build_page.py — встраивает dictionary.json в index.html.

index.html использует встроенный блок <script id="dict-data" type="application/json">,
чтобы работать по двойному клику (file://) без сервера, а также на GitHub Pages/http.
После перегенерации dictionary.json пайплайном запустите этот скрипт, чтобы страница
актуализировалась.

Использование:
    python3 build_page.py                # берёт ./dictionary.json → ./index.html
    python3 build_page.py --input d.json --output index.html
"""
import argparse
import json
import re
import sys
from pathlib import Path

MARKER_RE = re.compile(
    r'(<script id="dict-data" type="application/json">\s*)(.*?)(\s*</script>)',
    re.DOTALL,
)


def inject(html: str, data_text: str) -> str:
    m = MARKER_RE.search(html)
    if not m:
        raise SystemExit("Не найден блок <script id=\"dict-data\"> в index.html")
    return html[:m.start()] + m.group(1) + data_text + m.group(3) + html[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="dictionary.json", help="путь к dictionary.json (по умолчанию ./dictionary.json)")
    ap.add_argument("--html", default="index.html", help="путь к index.html (по умолчанию ./index.html)")
    args = ap.parse_args()

    src = Path(args.input)
    html_path = Path(args.html)
    if not src.exists():
        print(f"Нет файла {src}", file=sys.stderr)
        return 1
    if not html_path.exists():
        print(f"Нет файла {html_path}", file=sys.stderr)
        return 1

    data = json.load(src.open(encoding="utf-8"))
    data_text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    new_html = inject(html_path.read_text(encoding="utf-8"), data_text)
    html_path.write_text(new_html, encoding="utf-8")

    n_entries = sum(
        len(e.get("entries", []))
        for t in data.get("themes", [])
        for s in t.get("sections", [])
        for e in s.get("subsections", [])
    )
    print(f"✓ {src} → встроено в {html_path} "
          f"({len(data_text)} байт, тем: {len(data.get('themes', []))}, записей: {n_entries})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
