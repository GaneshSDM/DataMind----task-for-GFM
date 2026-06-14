#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")" || { echo "Failed to change directory"; exit 1; }
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
echo "DataMind DataFlow → http://localhost:8000"

