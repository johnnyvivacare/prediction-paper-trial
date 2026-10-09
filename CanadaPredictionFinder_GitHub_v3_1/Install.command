#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
trap 'code=$?; if [ "$code" -ne 0 ]; then printf "\nInstallation stopped safely. Read the error above.\n"; read -r -p "Press Return to close... " _ || true; fi' EXIT
printf '\nCanada Prediction Finder v3 — PAPER RESEARCH ONLY\n'
printf 'No account keys, purchases, remote install scripts, or live orders.\n\n'
PY=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  candidate_path="$(command -v "$candidate" 2>/dev/null || true)"
  if [ -n "$candidate_path" ] && "$candidate_path" -c 'import sys; assert sys.version_info >= (3,10); from zoneinfo import ZoneInfo; ZoneInfo("America/Vancouver")' >/dev/null 2>&1; then
    PY="$candidate_path"; break
  fi
done
if [ -z "$PY" ]; then
  printf 'Python 3.10 or newer with timezone data was not found.\nInstall a supported macOS Python from https://www.python.org/downloads/macos/ and run this again.\n'
  exit 1
fi
printf 'Using %s\n' "$PY"
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv --without-pip .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3,10)'
printf '\nRunning the offline test suite...\n'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py doctor
chmod +x ./*.command
printf '\nInstalled. Double-click Start.command for real-data PAPER research.\nDouble-click Demo.command for an explicitly fabricated offline preview.\nPrivate ledgers are stored outside this folder; updates do not reset balances.\n\n'
read -r -p 'Press Return to close... ' _ || true
