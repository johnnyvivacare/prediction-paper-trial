#!/bin/bash
set -u
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf 'Run Install.command first.\n'; read -r -p 'Press Return... ' _ || true; exit 1
fi
printf 'Current real-data PAPER ledger report. This does not change positions or cash.\n'
.venv/bin/python app.py report
code=$?
read -r -p 'Press Return to close... ' _ || true
exit "$code"
