#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then printf 'Run Install.command first.\n'; exit 1; fi
.venv/bin/python mac_autostart.py disable
read -r -p 'Press Return... ' _ || true
