#!/bin/sh
# Start the public demo (see the Dockerfile at the repository root): reseed the
# fictional school, run the worker in the background, then serve the interface
# and API on $PORT.
set -e

if [ -z "$HR_SECRET_KEY" ]; then
  # Sessions only need to survive this container, which reseeds on every start.
  HR_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
  export HR_SECRET_KEY
fi

python seed.py

python -m app.worker &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "*" --no-server-header
