#!/bin/bash
set -u
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf 'Run Install.command first.\n'; read -r -p 'Press Return... ' _ || true; exit 1
fi
printf 'Checking local setup and the official keyless public market-data endpoint...\n'
.venv/bin/python app.py doctor --network
code=$?
printf '\nA failed feed check means NO live-data verification. Do not bypass denied access or TLS checks.\n'
read -r -p 'Press Return to close... ' _ || true
exit "$code"
