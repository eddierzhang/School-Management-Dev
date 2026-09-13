# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [1.0.0] — 2026-09-13

The first production release: the student support dashboard, packaged to run
in a real school.

### Added

- **Accounts, roles and sign-in.** Administrator, counselor, teacher, registrar
  and business office roles, with a permission check on every route. Teachers
  see only students in their own sections. Password sign-in (scrypt) and
  sign-in through the school's identity provider (OpenID Connect with PKCE).
  Server-side sessions, CSRF protection and lockout after repeated failed
  sign-ins.
- **Audit log** of every change (including refused attempts), every view of a
  student's record, and every sign-in, with an Admin tab to search it.
- **Account management** on the Admin tab, and `python -m app.cli` commands for
  the first administrator, password resets and deactivation.
- **Student history:** daily snapshots of each student's indices, charted in the
  student record with plans and overrides marked.
- **Overrides:** counselors can mark a flag as known and in hand, or correct a
  band, with a reason and an end date.
- **Required reasons** when rejecting an agent's proposal, stored with who
  decided.
- **OneRoster 1.1 CSV import**, from the Admin tab or the command line. It checks
  the export before writing anything, can be re-run safely, marks dropped
  enrollments rather than deleting them, and can create teacher accounts.
- **Exempt scores**, which count as neither missing nor graded.
- **Background job queue** in the database, with a separate worker process,
  heartbeats, retries and recovery from a dead worker.
- **Optional modules** (`HR_MODULES`): registrar, stockroom, finance and the
  general manager are off by default.
- **Production deployment:** Dockerfiles, `docker-compose.prod.yml` with
  PostgreSQL, migrations, API, worker, Caddy (automatic HTTPS, security headers,
  Content Security Policy) and nightly verified backups, plus a restore script.
- **Operations:** `/api/health` and `/api/ready`, JSON logs that never contain
  student IDs, request IDs, optional Sentry reporting.
- **Alembic migrations** for the whole schema, with a test that the models and
  migrations agree.
- **Continuous integration:** lint, dependency audits, tests on SQLite and
  PostgreSQL, a startup smoke test, the frontend build, and the full production
  stack signed into end to end. Dependabot updates.
- Documentation in `docs/`.

### Changed

- The product is now centered on the student support workflow. The registrar
  console prototype and roster generator moved to `demo/`.
- "Today" is the real date unless `HR_TODAY` pins it for the demo.
- Courses the catalog marks ungraded no longer move students' indices.
- Summary figures are scoped to what the signed-in person may see.
- Every backend dependency was upgraded, clearing known vulnerabilities in
  Starlette and python-multipart.
- The local model is reached at `127.0.0.1` by default, which avoids a slow IPv6
  fallback on Windows.

### Fixed

- A failed approval no longer commits a partly applied change.
- The interface says when the model is not installed, instead of reporting that
  it cannot call tools.

### Removed

- Creating and altering tables at application startup.
- FastAPI background tasks and the in-memory agent dispatch queue.

## [0.1.0]

The original prototype: struggle and excelling indices, recommendations, support
plans, class and study plans, document reading, schedules, the stockroom and
budget, and the local agent fleet.

[1.0.0]: https://github.com/eddierzhang/School-Management-Dev/releases/tag/v1.0.0
