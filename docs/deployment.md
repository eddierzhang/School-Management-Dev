# Deployment and operations

- [The production stack](#the-production-stack)
- [First deployment](#first-deployment)
- [Upgrading](#upgrading)
- [Background jobs](#background-jobs)
- [Backups and restores](#backups-and-restores)
- [Monitoring](#monitoring)
- [Running the model](#running-the-model)
- [Checklist](#checklist)

## The public demo

The `Dockerfile` at the repository root is a different, smaller deployment: the
fictional school in one container, for showing the product, never for real
records. At build time it generates the demo roster and builds the interface.
At start, `deploy/demo-start.sh` reseeds SQLite, starts the worker in the
background and serves the interface and API on `$PORT`. It runs with
`HR_APP_ENV=demo`, which allows SQLite and the pinned demo clock, but still needs
a secret key (generated at start if none is given), marks cookies `Secure` and
hides the API schema.

**Render (free):** New → Blueprint → this repository. `render.yaml` defines one
free web service with a generated `HR_SECRET_KEY`, and redeploys on every push
to `main`. **Anywhere else:** `docker build -t student-support-demo .`, then run
it behind HTTPS with `PORT` set.

Anyone can sign in with the published demo password, and an administrator can
change things, so the demo resets on every restart. On Render's free plan that
happens whenever it wakes from sleep.

## The production stack

`docker-compose.prod.yml` runs the whole service on one host.

| Service | What it does |
|---|---|
| `db` | PostgreSQL 16 on a named volume |
| `migrate` | runs `alembic upgrade head`, then exits; the API and worker start only after it succeeds |
| `api` | the FastAPI application under uvicorn (two workers), reachable only through Caddy |
| `worker` | the job worker; given ten minutes to finish a job on shutdown |
| `web` | Caddy: HTTPS with automatic certificates, the built interface, `/api` proxied, security headers and CSP |
| `backup` | a nightly, verified `pg_dump`, kept for `HR_BACKUP_KEEP_DAYS` |
| `ollama` | optional (`--profile ollama`); most schools run the model on a separate GPU machine |

The API, worker and migration step run from one image (`backend/Dockerfile`, a
non-root user). The web image builds the interface and serves it with Caddy
(`frontend/Dockerfile`, `frontend/Caddyfile`).

## First deployment

You need a host with Docker and Docker Compose, and a DNS name pointing at it
with ports 80 and 443 open (Caddy obtains the certificate).

1. **Configure.**

   ```bash
   cp deploy/.env.example deploy/.env
   ```

   Set at least `HR_DOMAIN`, `HR_CORS_ORIGINS`, `HR_SECRET_KEY`,
   `POSTGRES_PASSWORD` and `HR_OLLAMA_URL`. Generate secrets with
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Every setting is described in [configuration](configuration.md).

2. **Start.**

   ```bash
   docker compose -f docker-compose.prod.yml --env-file deploy/.env up -d --build
   ```

3. **Create the first administrator.**

   ```bash
   docker compose -f docker-compose.prod.yml --env-file deploy/.env exec api \
     python -m app.cli create-user head@school.edu "Head of School" admin --password
   ```

4. **Sign in** at `https://HR_DOMAIN`, set up the identity provider if you use one,
   [import the roster](data-import.md), and add staff accounts on the Admin tab.

## Upgrading

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file deploy/.env up -d --build
```

`migrate` runs before the new API and worker start, so a new version never
serves an old schema. If a migration fails, the old containers are not replaced,
and `docker compose logs migrate` shows why.

## Background jobs

Agent runs, document reads and the daily history snapshot are jobs stored in the
database (`backend/app/jobs.py`) and run by the worker (`python -m app.worker`).
A request records a job and returns, so the web server never holds minutes of
model work and a restart loses nothing.

- **One model job at a time.** Agent runs and document reads are claimed only
  while no other is running, so Ollama serves one request. Run **one worker per
  model host**.
- **Recovery.** The worker heartbeats every 30 seconds. A running job silent for
  two minutes is put back on the queue. After its last attempt it is marked
  failed, along with the agent run or document it was for, so nothing stays
  "running" forever.
- **Retries** back off. A job with a unique key, such as the day's snapshot, is
  enqueued once however many workers ask.
- **Claiming** is a guarded `UPDATE`, atomic on PostgreSQL and SQLite, so two
  workers never run the same job.
- `python -m app.worker --drain` runs everything queued, then exits.

## Backups and restores

The `backup` service writes a compressed, custom-format dump to `HR_BACKUP_DIR`
once a day at `HR_BACKUP_HOUR` (UTC). It verifies the dump can be read, and
deletes dumps older than `HR_BACKUP_KEEP_DAYS`.

**Copy backups off the host.** A backup on the same disk as the database does not
survive that disk.

To restore:

```bash
deploy/restore.sh backups/halverson-20260912-0200.dump
```

The script asks for confirmation, stops the API and worker, restores into the
database, runs migrations (so an older dump is brought up to the current code),
and starts everything again. **Rehearse a restore on a copy before you need one.**

## Monitoring

| Endpoint | Meaning |
|---|---|
| `GET /api/health` | liveness: the process answers |
| `GET /api/ready` | readiness: the database answers and is at the newest migration. The worker and the model are reported but never make it fail. |

- **Logs** are JSON on stdout (`HR_LOG_FORMAT=json`): one access line per request
  with the route template, status, duration, request ID and user, plus job
  start and finish lines from the worker. Collect them with any Docker log
  driver.
- **Errors** go to Sentry when `HR_SENTRY_DSN` is set, with personal data off.
- **Alert on:** `/api/ready` failing, `checks.worker.worker_alive` false, a
  growing `checks.worker.queued`, and a missing nightly backup file.

## Running the model

The AI features need Ollama with a tool-capable model (`qwen3:4b` or larger).

- **Same host:** start with `--profile ollama`, set
  `HR_OLLAMA_URL=http://ollama:11434`, uncomment the GPU reservation in
  `docker-compose.prod.yml` if the host has an NVIDIA GPU, then
  `docker compose ... exec ollama ollama pull qwen3:4b`.
- **A separate GPU machine (recommended):** run Ollama there, reachable only from
  the application host, and set `HR_OLLAMA_URL` to it.

Without a model, everything except agent runs and document reads works, and the
interface explains what is missing.

## Checklist

- [ ] `HR_SECRET_KEY` and `POSTGRES_PASSWORD` are long and random, and `deploy/.env` is not in version control
- [ ] `HR_DOMAIN` and `HR_CORS_ORIGINS` match the public address
- [ ] `HR_TODAY` is not set
- [ ] Sign-in through the school's identity provider works; `HR_PASSWORD_LOGIN=false` once everyone uses it
- [ ] The first administrator exists, and demo accounts do not
- [ ] Backups are copied off the host, and a restore has been rehearsed
- [ ] `/api/ready` and the worker are monitored
- [ ] A retention policy for audit events, snapshots and transcripts is agreed
