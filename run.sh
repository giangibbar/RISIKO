#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
echo "🎲 RISIKO — http://localhost:8080"
uvicorn server.main:app --host 0.0.0.0 --port 8080
