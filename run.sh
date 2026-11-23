#!/usr/bin/env bash
#
# Распознать фото книги → dictionary.json.
#
# Запуск:
#   ./run.sh [INPUT_DIR] [OUTPUT_JSON]
#
#   INPUT_DIR   — папка с фото (*.jpg/*.jpeg/*.png). По умолчанию текущая папка.
#   OUTPUT_JSON — куда положить результат. По умолчанию dictionary.json.
#
# Переменные окружения:
#   VENV        — путь к виртуальному окружению (по умолчанию ./venv)
#   CANONICAL   — путь к overlay-файлу с чистыми названиями разделов/подразделов
#                 (по умолчанию canonical_verbs.json, если существует).
#                 Для НОВЫХ разделов книги (не глаголы) — удалите файл или
#                 unset CANONICAL, тогда названия берутся из OCR как есть.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INPUT="${1:-.}"
OUT="${2:-dictionary.json}"
VENV="${VENV:-$SCRIPT_DIR/venv}"
PY="$VENV/bin/python"

# --- 1. окружение ---
if [ ! -x "$PY" ]; then
  echo "[setup] creating venv at $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade -q pip
  "$VENV/bin/pip" install -q easyocr pillow scipy
fi

# --- 2. OCR ---
"$PY" ocr_all.py --input "$INPUT" --output ocr_raw.json

# --- 3. парсер: OCR → события ---
"$PY" parse6.py --input ocr_raw.json --output events.json --img-dir "$INPUT"

# --- 4. сборка дерева ---
CANON_FLAG=""
if [ -n "${CANONICAL:-}" ] && [ -f "$CANONICAL" ]; then
  CANON_FLAG="--canonical $CANONICAL"
elif [ -f "$SCRIPT_DIR/canonical_verbs.json" ]; then
  CANON_FLAG="--canonical $SCRIPT_DIR/canonical_verbs.json"
fi
# shellcheck disable=SC2086
"$PY" build_json.py --input events.json --output "$OUT" $CANON_FLAG

echo
echo "done -> $OUT"
"$PY" - <<PY
import json
d=json.load(open("$OUT",encoding="utf-8"))
ne=sum(len(ss['entries']) for s in d['sections'] for ss in s['subsections'])
print(f"sections={len(d['sections'])} subsections={sum(len(s['subsections']) for s in d['sections'])} entries={ne}")
PY
