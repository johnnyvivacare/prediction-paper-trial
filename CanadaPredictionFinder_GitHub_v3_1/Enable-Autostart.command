#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then printf 'Run Install.command first.\n'; exit 1; fi
printf 'OPTIONAL: start paper research when you log into this Mac.\nStop the foreground scanner first (Control-C). Keep this folder in its permanent location.\n'
read -r -p 'Type ENABLE to install the login agent: ' choice
if [ "$choice" = 'ENABLE' ]; then .venv/bin/python mac_autostart.py enable; else printf 'No change made.\n'; fi
read -r -p 'Press Return... ' _ || true
