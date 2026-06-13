#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
echo "DataMind DataFlow → http://localhost:8000"
uvicorn app:app --host 0.0.0.0 --port 8000
