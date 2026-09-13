# Configuration

All settings are environment variables prefixed with `HR_`. The application reads
them from the environment, or from `backend/.env` in development. In production,
`docker-compose.prod.yml` reads `deploy/.env`. The source of truth is
`backend/app/config.py`.

## Application

| Setting | Default | Description |
|---|---|---|
| `HR_APP_ENV` | `development` | `development`, `test` or `production`. Production enables the [startup safeguards](security.md#production-safeguards). |
| `HR_DATABASE_URL` | `sqlite:///./halverson.db` | SQLAlchemy URL. Production requires PostgreSQL: `postgresql+psycopg://user:pass@host:5432/db`. |
| `HR_CORS_ORIGINS` | `http://localhost:5174,…` | Comma-separated origins allowed to call the API from a browser. |
| `HR_SCHOOL_NAME` | `Halverson Ridge High School` | Your school's name, shown in the interface. The default is the fictional demo school. |
| `HR_TERM` | `Fall 2026` | The current term's name. |
| `HR_TODAY` | *(unset)* | Pins "today" for the demo data. Leave unset in production. |
| `HR_MODULES` | *(empty)* | Optional modules: `registrar`, `stockroom`, `finance`, `manager`, comma-separated, or `all`. |

## Sign-in

| Setting | Default | Description |
|---|---|---|
| `HR_SECRET_KEY` | development value | Signs the OIDC state cookie. At least 32 random characters in production. |
| `HR_SESSION_HOURS` | `12` | How long a session lasts. |
| `HR_COOKIE_SECURE` | *(production)* | Force the `Secure` cookie flag on or off. Defaults to on in production. |
| `HR_PASSWORD_LOGIN` | `true` | Allow email and password sign-in. |
| `HR_LOGIN_MAX_FAILURES` | `5` | Failed attempts before an email is locked out. |
| `HR_LOGIN_LOCKOUT_MINUTES` | `15` | How long a lockout lasts. |
| `HR_OIDC_ISSUER` | *(empty)* | The identity provider's issuer URL. Setting it and the client ID enables school sign-in. |
| `HR_OIDC_CLIENT_ID` | *(empty)* | OAuth client ID. |
| `HR_OIDC_CLIENT_SECRET` | *(empty)* | OAuth client secret. |
| `HR_OIDC_REDIRECT_URI` | *(empty)* | `https://your-domain/api/auth/oidc/callback` |
| `HR_OIDC_SCOPES` | `openid email profile` | Requested scopes. |
| `HR_OIDC_BUTTON_LABEL` | `Sign in with your school account` | Label on the sign-in screen. |

Common issuers: Google Workspace `https://accounts.google.com`; Microsoft Entra
`https://login.microsoftonline.com/<tenant-id>/v2.0`.

## Local model

| Setting | Default | Description |
|---|---|---|
| `HR_OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama listens. |
| `HR_OLLAMA_MODEL` | `qwen3:4b` | A model with the `tools` capability. |
| `HR_OLLAMA_TIMEOUT` | `300` | Seconds to wait for one model reply. |
| `HR_OLLAMA_TEMPERATURE` | `0.1` | Sampling temperature. |
| `HR_OLLAMA_NUM_CTX` | `16384` | Context window sent with every request. Ollama's own default silently truncates. |
| `HR_AGENT_MAX_STEPS` | `8` | Most model turns in one agent run. |
| `HR_AGENT_MAX_SECONDS` | `420` | Wall-clock limit for one agent run. |

## Support policy

| Setting | Default | Description |
|---|---|---|
| `HR_SUPPORT_THRESHOLD` | `72` | A course grade below this needs a plan. |
| `HR_CONCERN_FLOOR` | `65` | Below this, tutoring rather than monitoring. |
| `HR_EXCELLING_THRESHOLD` | `86` | At or above this, enrichment is on the table. |

The index weights and band cut-offs are code, not configuration: see the top of
`backend/app/analytics.py` and [the support engine](support-engine.md#the-indices).

## Operations

| Setting | Default | Description |
|---|---|---|
| `HR_SNAPSHOT_HOUR` | `17` | UTC hour after which the worker takes the day's history snapshot. |
| `HR_WORKER_POLL_SECONDS` | `2` | How often an idle worker checks the queue. |
| `HR_LOG_FORMAT` | `text` | `text`, or `json` for a log collector. Production compose sets `json`. |
| `HR_LOG_LEVEL` | `INFO` | Log level. |
| `HR_SENTRY_DSN` | *(empty)* | Report errors to Sentry, with personal data off. |

## Deployment only (`deploy/.env`)

| Setting | Description |
|---|---|
| `HR_DOMAIN` | The public host name Caddy serves and obtains a certificate for. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database credentials; also used to build `HR_DATABASE_URL`. |
| `HR_BACKUP_DIR` | Host directory for nightly dumps (default `./backups`). |
| `HR_BACKUP_KEEP_DAYS` | Days of dumps to keep (default `14`). |
| `HR_BACKUP_HOUR` | UTC hour for the nightly dump (default `2`). |
| `HR_VERSION` | Tag for the built images (default `latest`). |
