#!/usr/bin/env bash
# Start the support API and the interface together. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"

[ -d backend/.venv ] || { echo "No backend/.venv — see README, 'First run'."; exit 1; }
[ -d frontend/node_modules ] || { echo "No frontend/node_modules — run: cd frontend && npm install"; exit 1; }
# The demo data is built for this date; backend/.env or the environment can override it.
export HR_TODAY="${HR_TODAY:-2026-09-12}"
[ -f backend/halverson.db ] || { echo "No database yet — seeding."; (cd backend && .venv/bin/python seed.py); }
(cd backend && .venv/bin/alembic upgrade head)

# The fleet needs Ollama with a tool-capable model. Not fatal: everything except
# the Agents tab works without it, and that tab explains itself when it is missing.
if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  MODEL="${HR_OLLAMA_MODEL:-qwen3:4b}"
  if ! ollama list 2>/dev/null | grep -q "^${MODEL%%:*}"; then
    echo "  note: Ollama is up but $MODEL is not installed — run: ollama pull $MODEL"
  fi
else
  echo "  note: Ollama is not running, so the agent fleet is unavailable."
  echo "        Start it with 'ollama serve'. Everything else works without it."
fi

trap 'kill 0' EXIT INT TERM
(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
echo
echo "  API        http://localhost:8000/api/health"
echo "  API docs   http://localhost:8000/docs"
echo "  Interface  http://localhost:5174"
echo "  Agents     http://localhost:5174/#/agents"
echo
wait
