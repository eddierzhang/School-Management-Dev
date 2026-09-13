# Contributing

Thank you for helping improve Halverson Ridge Student Support.

## Getting started

Set up a local environment by following [docs/development.md](docs/development.md).
The demo data and demo accounts let you exercise every role without real records.

## Making a change

1. **Branch from `main`.**
2. **Keep the rules the codebase depends on:**
   - every API route checks a permission, and student data passes teacher scoping
   - a model change ships with an Alembic migration
   - agents only propose; changes are applied by the executor after approval
   - slow work goes through the job queue
   - no student data in logs
3. **Add or update tests.** A bug fix comes with a test that fails without it.
4. **Run the checks** before pushing:

   ```bash
   cd backend  && .venv/bin/ruff check . && .venv/bin/python -m pytest -q
   cd frontend && npm run typecheck && npm run build
   ```

5. **Update the documentation** in `docs/` when behavior or configuration
   changes, and add an entry under *Unreleased* in [CHANGELOG.md](CHANGELOG.md).
6. **Open a pull request.** CI must pass, including the PostgreSQL tests and the
   production stack check.

## Commit messages

Write the subject in the imperative mood ("Require a reason when rejecting a
proposal"), and use the body to explain why the change was made.

## Real data

Never commit real student data, real school exports or production settings. Use
the demo seed and fictional samples. `deploy/.env`, `backend/.env`, databases and
backups are ignored by Git; keep it that way.

## Security issues

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
