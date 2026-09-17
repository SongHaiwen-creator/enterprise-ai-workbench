# PostgreSQL Alpine-to-pgvector Volume Migration

This runbook moves the local PostgreSQL 17 databases from the legacy
Alpine/musl physical volume to a new Debian/Trixie pgvector volume by logical
backup and restore. Never attach the legacy physical volume to an image from a
different libc family.

## Approval gate

Do not execute this runbook without immediate human approval for the named
development database and volumes. Implementing Feature 008 does not authorize
the operational migration.

Never run `docker compose down -v`. Never delete, rename, overwrite, or reuse
the legacy `enterprise-ai-workbench_postgres_data` volume. The application must
remain stopped for writes from the first backup until validation completes.

## Preconditions

1. Record `docker compose ps`, the source image ID, PostgreSQL version, database
   list, Alembic revision, and both source and target volume names.
2. Resolve the exact source volume and verify it is
   `enterprise-ai-workbench_postgres_data` before any command that mounts it.
3. Create a separate host backup directory with sufficient free space and
   restrict access because dumps contain application data and database roles.
4. Stop every application process that can write to PostgreSQL. Keep only the
   already-running source PostgreSQL container available for the logical dump;
   do not change the image attached to its volume.

## Logical backup

1. Export globals and roles with `pg_dumpall --globals-only`.
2. List all non-template databases and create a custom-format `pg_dump` for
   each required application database, including the configured test database
   when it must be preserved.
3. Capture per-table row counts, installed extensions, constraints, database
   collations, and the current Alembic revision from the source.
4. Verify every dump with `pg_restore --list` and record checksums for all dump
   files before stopping the source container.

Do not place dump files in the repository and do not commit them.

## Initialize and restore

1. Stop the source container without `-v`. Confirm the legacy volume still
   exists and is not mounted by the new service.
2. Start `pgvector/pgvector:0.8.6-pg17-trixie` with the new
   `enterprise-ai-workbench_postgres_pgvector_data` volume declared by
   `compose.yaml`.
3. Confirm PostgreSQL major version 17 and that the server is healthy.
4. Restore required globals/roles, create the target databases, and restore
   each custom-format dump with `pg_restore --exit-on-error`.
5. Run Alembic upgrade to the approved head only after the restored revision
   has been recorded.

## Validation

1. Compare source and target database lists and per-table row counts.
2. Verify expected primary, unique, foreign-key, and check constraints,
   including the composite Workspace ownership constraints.
3. Verify `vector` is installed at the expected version and vector columns have
   the expected dimensions.
4. Compare database collation settings. Because logical restore rebuilds
   indexes under the target libc, run `REINDEX DATABASE` only if PostgreSQL
   reports a collation-version mismatch or validation identifies an affected
   index; record every rebuild.
5. Verify `alembic current`, run `alembic check`, then run the full backend
   PostgreSQL suite and application smoke tests against the restored target.
6. Resume writes only after every validation passes.

## Rollback

If restore or validation fails, stop application writes and the target
container. Do not delete either volume. Restore the previous Compose
configuration and start the source using the same image/libc family that was
attached when the logical backup was taken. Re-run source health and row-count
checks before resuming the application.

The legacy volume remains the rollback source until a later, separately
approved retention decision. Removal is never part of this runbook.
