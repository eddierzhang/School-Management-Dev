# Development

- [Setup](#setup)
- [Demo accounts](#demo-accounts)
- [Running](#running)
- [Database and migrations](#database-and-migrations)
- [Tests and checks](#tests-and-checks)
- [Continuous integration](#continuous-integration)
- [Project layout](#project-layout)
- [Conventions](#conventions)

## Setup

Requirements: Python 3.11, Node 20+, Git Bash or another POSIX shell for
`dev.sh`, and optionally [Ollama](https://ollama.com) with `qwen3:4b` for the AI
features.

```bash
node demo/gen_seed.js                                   # the demo roster, written to demo/seed/

python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env                    # pins the demo clock, turns on every module
(cd backend && .venv/bin/python seed.py)                # migrates and seeds backend/halverson.db

(cd frontend && npm install)
```

On Windows the virtual environment's scripts are in `backend/.venv/Scripts/`.

The demo term is built around 2026-09-12, so the seed refuses to run unless
`HR_TODAY=2026-09-12`, and the application should run with the same value.

`python seed.py --upgrade` adds sections missing from an existing database
without touching plans, proposals or documents.

## Demo accounts

Every demo account uses the password `halverson-demo-2026`.

| Account | Role |
|---|---|
| `admin@halverson.example.edu` | Administrator |
| `counselor@halverson.example.edu` | Counselor |
| `registrar@halverson.example.edu` | Registrar |
| `business@halverson.example.edu` | Business office |
| `r.okonkwo@halverson.example.edu` (and one per teacher: `s.frankel@`, `a.ferraro@`, …) | Teacher |

## Running

```bash
./dev.sh
```

`dev.sh` starts the API on port 8000, the worker, and the interface on port 5174.
To run them separately:

```bash
cd backend  && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
cd backend  && .venv/bin/python -m app.worker
cd frontend && npm run dev            # HR_API_URL=http://127.0.0.1:8010 for an API on another port
```

- Interface: http://localhost:5174
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health and `/api/ready`

The Vite dev server proxies `/api`, so the browser stays same-origin and the
session cookie is first-party. The URL is the view: `#/students`,
`#/classes/MAT-150`, `#/students/S-1507`.

Without the worker, agent runs, document reads and snapshots wait in the queue.

## Database and migrations

SQLite is the development default. For PostgreSQL:

```bash
docker compose up -d db
export HR_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/educationhack
```

The schema is owned by Alembic (`backend/alembic/versions/`). The application
never creates or alters tables; `/api/ready` returns `503` until the database is
at the newest migration.

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "what changed"   # after changing app/models.py
```

A test fails if the models and migrations disagree, so a model change without a
migration cannot be merged. Autogenerate is configured to write portable SQL
(for example `func.now()` rather than Postgres's `now()`), and batch mode keeps
migrations working on SQLite. Review every generated migration before committing.

## Tests and checks

```bash
cd backend
.venv/bin/python -m pytest -q                                         # SQLite
HR_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/educationhack_test \
  .venv/bin/python -m pytest -q                                       # PostgreSQL (drops that database's tables)
.venv/bin/ruff check .
.venv/bin/pip-audit -r requirements.txt

cd ../frontend
npm run typecheck
npm run build
```

The suite seeds its own database and never touches the development one. Tests
that write (imports, overrides, the job queue) clean up after themselves or roll
back.

Notable suites:

| File | Covers |
|---|---|
| `test_analytics.py` | the indices, on purpose-built records, including calibration regressions |
| `test_auth.py` | every role through real routes, teacher scoping, CSRF, lockout, the audit log, OIDC against a fake provider |
| `test_agents.py`, `test_manager.py` | tool validation, the proposal boundary, executor staleness checks, dispatch |
| `test_history.py` | snapshots, overrides, rejection reasons |
| `test_import.py` | OneRoster validation, idempotent re-import, dropped enrollments, exempt scores |
| `test_jobs.py` | claiming, retries, recovery from a dead worker, the daily snapshot |
| `test_platform.py` | migrations match the models, health and readiness |

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on `main`:

1. **Backend lint and audit:** ruff and pip-audit.
2. **Backend tests** on SQLite and PostgreSQL 16.
3. **Startup smoke test:** migrate an empty PostgreSQL database, start the API in
   production mode, and wait for `/api/ready`.
4. **Frontend:** typecheck, production build, `npm audit`.
5. **Production stack:** build both images, start `docker-compose.prod.yml`,
   check readiness through Caddy, create an administrator and sign in end to
   end.

Dependabot opens weekly grouped updates for pip, npm and Docker images, and
monthly updates for GitHub Actions.

## Project layout

```
backend/
  app/
    main.py            application setup, middleware, router mounting
    config.py          settings (HR_*)
    models.py          database models
    schemas.py         API response shapes, mirrored by frontend/src/types.ts
    analytics.py       the signal engine
    history.py         snapshots and a student's timeline
    class_plans.py     class performance and improvement plans
    study_plans.py     a student's class work and study plans
    schedule.py        the timetable and clash detection
    timetable.py       opening classes and sections
    importer.py        OneRoster import
    jobs.py            the job queue
    worker.py          the job worker
    audit.py           the audit log and access logging
    observability.py   log format and Sentry
    cli.py             administrative commands
    auth/              passwords, sessions, permissions, teacher scope, OIDC
    ai/                agents, tools, runner, executor, documents, Ollama client
    routers/           API routes
  alembic/             migrations
  tests/
  seed.py              the demo data
frontend/
  src/
    App.tsx            layout, tabs, routing
    auth.tsx           the signed-in person and their permissions
    api.ts             typed API client
    views/             one component per tab, plus sign-in and admin
    components/        shared components: charts, student record, plans, agent fleet
  Caddyfile            production web server
deploy/                production settings template, backup and restore
demo/                  demo roster generator and the registrar console prototype
docs/                  guides
```

## Conventions

- **Every route checks a permission.** Use `require("…")` or
  `require_by_method`. Student data must also pass `ensure_student` or
  `ensure_course` so teachers stay scoped.
- **Schema changes ship with a migration.**
- **Agents never write.** A new capability is a `propose_*` tool plus an executor
  handler that re-validates against current state. Add its permission to
  `PROPOSAL_PERMISSION`.
- **Slow work is a job.** Enqueue it with `jobs.enqueue`; do not start threads or
  use FastAPI background tasks.
- **No student data in logs.** Log route templates and IDs of jobs, not records.
- Commit messages describe the change in the imperative mood and explain why.
