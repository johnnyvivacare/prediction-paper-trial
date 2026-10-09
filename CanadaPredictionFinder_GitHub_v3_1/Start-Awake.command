#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf 'Run Install.command first.\n'; read -r -p 'Press Return... ' _ || true; exit 1
fi
if [ ! -x /usr/bin/caffeinate ]; then printf 'This option requires macOS. Use Start.command instead.\n'; exit 1; fi
printf 'Prevents idle system sleep while the bot runs. Keep the lid open and connect power.\nDoes not override forced sleep, shutdown, closing the lid, or network failures.\n'
/usr/bin/caffeinate -i .venv/bin/python app.py run --open
