#!/usr/bin/env bash
# Animal Video Engine - one-command start for Linux / macOS (no Docker needed).
set -euo pipefail
cd "$(dirname "$0")/.."

command -v ffmpeg >/dev/null || { echo "[!] FFmpeg not found (apt install ffmpeg / brew install ffmpeg)"; exit 1; }

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -q -r backend/requirements.txt
[ -f backend/.env ] || cp backend/.env.example backend/.env

if [ ! -f frontend/dist/index.html ]; then
  command -v npm >/dev/null || { echo "[!] Node.js needed once to build the UI"; exit 1; }
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

echo
echo "  Engine running at  http://localhost:8000   (Ctrl+C to stop)"
echo
cd backend
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
