# Operations guide

## Fresh clone

```powershell
Copy-Item .env.example .env
# Set private database, JWT, admin and Fernet values in .env.
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec backend python -m scripts.bootstrap_admin --email you@example.com
```

The bootstrap CLI uses hidden password prompts, the existing password policy and an
advisory lock. It creates only the first Super Admin and has no unauthenticated API.
Email delivery defaults to disabled. Never pass passwords or secrets on a command line.

## Services and data safety

The base Compose file provisions an independent PostgreSQL/pgvector service named
`postgres` (pgvector 0.8.7 on PostgreSQL 16) for new installations, plus backend,
frontend and two idle email workers. A read-only init script creates the `vector`
extension idempotently when a new volume is initialized. Existing persistent volumes
are not reinitialized; verify/upgrade them separately after a backup.
Use only private, ignored overrides for an existing deployment. Never mount an
existing recovery volume into a fresh clone, and never use `down --volumes` or
`--remove-orphans` during routine operations.

Workers remain alive but perform no database or SMTP polling while
`EMAIL_DELIVERY_ENABLED=false`.

```powershell
docker compose up -d --wait
docker compose ps
docker compose stop
```

Verification and notification workers are separate services. In-app bell
notifications are database records and are distinct from outgoing email. Test mode
requires a private recipient allowlist and rejects other envelope recipients before
SMTP; production delivery requires a separately approved change.

## Database and migrations

Run the read-only audit with `python -m scripts.audit_database` from `backend`.
Migrations `001` through `009` are ordered SQL files and are not tracked by a version
ledger. Apply them only after a verified private backup. `create_all()` is not a
replacement for migrations.

Before any live schema or data change, create a timestamped custom-format dump and
verify it with `pg_restore --list` and an isolated restore. Keep dumps, role exports,
credentials and rollback snapshots outside Git. Rollback means restoring into a new
isolated database, validating it, then explicitly switching services; never overwrite
an active database or delete its volume.

## Testing and troubleshooting

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
cd frontend; npm.cmd test -- --reporter=dot; npm.cmd run build
docker compose config --quiet
```

Automated tests use only the isolated test database and mocked SMTP/provider calls.
Live Gemini, SMTP and browser-account tests are optional and must use sanitized,
disposable fixtures. Keep `.env`, `secrets/`, migration overrides and private
archives ignored and out of release commits.

Customer registration intentionally creates an unverified account and queues a
verification message. With delivery disabled, login remains blocked until the user
verifies through `/auth/verify-email`; configure a private SMTP sender and test-mode
recipient allowlist for an isolated onboarding test. No verification bypass is
provided.
