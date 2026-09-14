# The public demo: the fictional Halverson Ridge High School in one container.
# The interface, API and worker run together on SQLite, and every start reseeds
# the demo, so the site resets itself whenever the host restarts it.
#
#   docker build -t student-support-demo .
#   docker run -p 8000:8000 -e HR_SECRET_KEY=$(openssl rand -hex 32) student-support-demo
#
# A real school uses docker-compose.prod.yml instead (PostgreSQL, Caddy, backups);
# see docs/deployment.md.

FROM node:22-alpine AS interface
WORKDIR /src
COPY demo/gen_seed.js demo/gen_seed.js
RUN node demo/gen_seed.js > /dev/null
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY frontend frontend
RUN cd frontend && npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/alembic.ini backend/seed.py ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=interface /src/demo/seed /demo/seed
COPY --from=interface /src/frontend/dist /srv
COPY deploy/demo-start.sh /demo-start.sh
RUN mkdir /app/data && chown app:app /app/data

ENV HR_APP_ENV=demo \
    HR_DATABASE_URL=sqlite:////app/data/halverson.db \
    HR_SEED_DIR=/demo/seed \
    HR_STATIC_DIR=/srv \
    HR_TODAY=2026-09-12 \
    HR_MODULES=all \
    HR_LOG_FORMAT=json \
    PORT=8000

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4).status == 200 else 1)"

CMD ["sh", "/demo-start.sh"]
