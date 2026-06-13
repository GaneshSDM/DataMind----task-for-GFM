@echo off
cd /d %~dp0
python -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
echo DataMind DataFlow -> http://localhost:8000
uvicorn app:app --host 0.0.0.0 --port 8000
