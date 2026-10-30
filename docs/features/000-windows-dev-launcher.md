# Windows local development launcher

User-requested developer tooling, independent of the product roadmap.
Issue: #56. Branch: `feat/windows-dev-launcher`.

## Goal

Start the existing local Workbench environment by double-clicking a Windows file.

## Scope

- Root CMD entry point and Windows PowerShell 5.1-compatible launcher.
- Resolve an explicitly supplied project root, the adjacent prepared checkout,
  or the prepared primary checkout of the same Git worktree repository.
- Start Docker Desktop when needed and start only the existing Compose
  `postgres_pgvector` container; do not create a replacement database.
- Read-only configuration, connectivity and Alembic revision check.
- Reuse healthy Workbench services, start absent services on localhost ports
  8000/3000, refuse occupied incompatible ports, wait with deadlines and logs.
- Open the workbench in the default browser; provide a desktop shortcut locally.

## Business rules

No migrations, dependency installs, volume changes, server process killing, socket
repair, authentication changes or external AI calls. Errors remain visible in
the double-click window. Repeated/concurrent launches must not duplicate servers.
Existing secrets are loaded only in the backend process, never copied or printed.

## API / data contract

`Start-Workbench.cmd` calls `scripts/start-workbench.ps1`. Optional `-ProjectRoot`
selects a prepared checkout; `-NoBrowser` supports verification. Runtime logs
are stored under `.cache/dev-services` in that checkout. Existing `/health`,
`/openapi.json` and `/app` remain unchanged. No application contract changes.

## Acceptance criteria

- Double click starts the prepared environment and opens `/app` after all checks.
- Warm launch succeeds without starting duplicate frontend/backend processes.
- An absent configuration/dependency, schema mismatch, incompatible occupied
  port, missing DB container or Docker startup failure produces a bounded error.
- Database revisions/data and user files are unchanged by launching.
- Entry point works from another current directory and project paths with spaces.

## Test requirements

PowerShell 5.1 parse check, focused root/port/HTTP failure-path checks, read-only
DB helper checks, real cold/warm launch smoke verification and diff review.
Application pytest/PostgreSQL mutation suites and frontend builds are not gates
for this tooling-only change: no application source, schema or dependency changes.

## Out of scope

Product features, production deployment, environment bootstrap, automatic repair,
shutdown manager, automatic migration, automatic login and automatic merge.

## Verification (2026-10-30, Asia/Shanghai)

- Windows PowerShell 5.1 parser and focused checks passed: missing/unprepared
  explicit roots, synthetic root with spaces, unavailable/unrelated HTTP servers,
  valid API identity, prefixed Workbench title, busy/free ports and probe timeout.
- Ruff passed for the Python preflight helper. Error output uses fixed messages.
- Existing stopped PostgreSQL container restored and read-only schema check passed.
- Real frontend cold start passed. For backend cold verification, the existing
  Uvicorn reload child's process was explicitly identified and stopped manually;
  the launcher then started a new backend successfully. The launcher never kills
  existing application servers itself.
- Consecutive warm launches passed; both HTTP readiness checks passed.
- Installed CMD invoked successfully from TEMP (different working directory),
  resolving the prepared primary checkout. Desktop shortcut created and browser opened.
- No migrations, dependency installs, provider calls or database data edits.
- Self-review and whitespace check passed. No application suites/build rerun:
  application code and dependencies are unchanged; checks are scoped to tooling.
- Docker-down startup logic is bounded and reports failure, but a full Docker
  Desktop shutdown/restart was not forced as part of this verification.
- Socket corruption still requires manual Docker troubleshooting; this launcher
  deliberately performs no automatic socket/data repair.
