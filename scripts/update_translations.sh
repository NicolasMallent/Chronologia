#!/usr/bin/env bash
# Extrait les textes à traduire (langue source : français), complète EN/ES, compile les .qm.
# Usage : scripts/update_translations.sh   (depuis la racine, venv activé ou .venv présent)
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=".venv/bin"; [ -x "$BIN/pyside6-lupdate" ] || BIN=""
SRC=(src/chronologia/*.py)
for lang in en es; do
    ${BIN:+$BIN/}pyside6-lupdate "${SRC[@]}" -source-language fr -target-language "$lang" \
        -ts "src/chronologia/translations/chronologia_${lang}.ts" -no-obsolete
done
python3 scripts/fill_translations.py   # complète les nouveaux textes (dictionnaire du script)
for lang in en es; do
    ${BIN:+$BIN/}pyside6-lrelease "src/chronologia/translations/chronologia_${lang}.ts" \
        -qm "src/chronologia/translations/chronologia_${lang}.qm"
done
