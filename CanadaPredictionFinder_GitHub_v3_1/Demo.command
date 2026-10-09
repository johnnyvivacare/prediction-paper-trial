#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf 'Run Install.command first.\n'; read -r -p 'Press Return... ' _ || true; exit 1
fi
printf 'DEMO uses fabricated prices and a separate ledger. NOT proof of profit.\n'
.venv/bin/python app.py demo --open --port 8766 || { code=$?; read -r -p 'Press Return to close... ' _ || true; exit "$code"; }
