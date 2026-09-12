#!/usr/bin/env bash
# Start the support API and the interface together. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"

[ -d backend/.venv ] || { echo "No backend/.venv — see README, 'First run'."; exit 1; }
[ -d frontend/node_modules ] || { echo "No frontend/node_modules — run: cd frontend && npm install"; exit 1; }
[ -f backend/halverson.db ] || { echo "No database yet — seeding."; (cd backend && .venv/bin/python seed.py); }

trap 'kill 0' EXIT INT TERM
(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
echo
echo "  API        http://localhost:8000/api/health"
echo "  API docs   http://localhost:8000/docs"
echo "  Interface  http://localhost:5174"
echo
wait
