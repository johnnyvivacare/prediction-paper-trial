#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf 'Run Install.command first.\n'; read -r -p 'Press Return... ' _ || true; exit 1
fi
.venv/bin/python app.py run --open || { code=$?; read -r -p 'Press Return to close... ' _ || true; exit "$code"; }
