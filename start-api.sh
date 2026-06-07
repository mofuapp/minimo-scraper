#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -r requirements-api.txt
playwright install chromium

export MINIMO_CORS_ORIGINS="${MINIMO_CORS_ORIGINS:-http://localhost:8080,http://127.0.0.1:8080}"
uvicorn api:app --reload --host 0.0.0.0 --port 8000
