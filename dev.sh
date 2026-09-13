#!/usr/bin/env bash
# Start the API, the worker and the interface together. Ctrl-C stops all three.
# On Windows, dev.ps1 does the same from PowerShell.
set -euo pipefail
cd "$(dirname "$0")"

# The virtual environment keeps its programs in bin/ on macOS and Linux, Scripts/ on Windows.
if [ -x backend/.venv/bin/python ]; then BIN=.venv/bin; elif [ -x backend/.venv/Scripts/python.exe ]; then BIN=.venv/Scripts; else
  echo "No backend/.venv — see docs/development.md (Setup)."; exit 1; fi
[ -d frontend/node_modules ] || { echo "No frontend/node_modules — run: cd frontend && npm install"; exit 1; }
[ -d demo/seed ] || { echo "Generating the demo roster."; node demo/gen_seed.js >/dev/null; }
[ -f backend/.env ] || { cp backend/.env.example backend/.env; echo "Created backend/.env from .env.example."; }

# The demo data is built for this date; backend/.env or the environment can override it.
export HR_TODAY="${HR_TODAY:-2026-09-12}"
export HR_MODULES="${HR_MODULES:-all}"      # the demo shows every module
[ -f backend/halverson.db ] || { echo "No database yet — seeding."; (cd backend && $BIN/python seed.py >/dev/null); }
(cd backend && $BIN/python -m alembic upgrade head >/dev/null 2>&1)

# The first free port from 8000 up, so another project already on 8000 does not get in the way.
API_PORT=$(cd backend && $BIN/python -c "
import socket
p = 8000
while True:
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', p)); break
        except OSError:
            p += 1
print(p)")
export HR_API_URL="http://127.0.0.1:$API_PORT"      # where the interface sends /api

# The agents need Ollama with a tool-capable model. Not fatal: everything else works without it.
if ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "  note: Ollama is not running, so the AI agents are unavailable. Everything else works."
fi

trap 'kill 0' EXIT INT TERM
(cd backend && $BIN/python -m uvicorn app.main:app --reload --port "$API_PORT") &
(cd backend && $BIN/python -m app.worker) &      # agent runs, document reads, daily snapshots
(cd frontend && npm run dev) &
echo
echo "  API        http://localhost:$API_PORT/api/health   (docs: /docs)"
echo "  Interface  the Local address Vite prints (normally http://localhost:5174)"
echo "  Sign in    counselor@halverson.example.edu / halverson-demo-2026"
echo
wait
