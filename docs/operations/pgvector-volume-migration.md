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

Do not use `docker compose start`, `docker compose start postgres`, or
`docker start` on an old PostgreSQL container during this migration. Those
commands start an existing container without reconciling its image or mounts.
An old container can therefore still pair the Debian pgvector image with the
legacy Alpine-created physical volume even though `compose.yaml` has changed.

The current service is intentionally named `postgres_pgvector`, not
`postgres`. Its distinct Compose identity prevents normal commands for the
current project from selecting the stale `postgres` service container.

## Stale-container preflight

Complete and record this preflight before starting any PostgreSQL container:

1. Render the current definition with `docker compose config` and confirm that
   its only PostgreSQL service is `postgres_pgvector`, its image is
   `pgvector/pgvector:0.8.6-pg17-trixie`, and its data mount source resolves to
   `enterprise-ai-workbench_postgres_pgvector_data` at
   `/var/lib/postgresql/data`.
2. List all containers for the project, including stopped containers, with
   `docker compose ps --all` and:

   ```text
   docker ps --all --filter label=com.docker.compose.project=enterprise-ai-workbench
   ```

3. Inspect every current or historical PostgreSQL container before any start
   or removal operation:

   ```text
   docker inspect <container-id> --format 'name={{.Name}} image={{.Config.Image}}{{range .Mounts}} mount={{.Type}}:{{.Name}}->{{.Destination}}{{end}}'
   ```

   Record the exact container ID, image ID/name, running state, Compose service
   label, mount type, volume name, and destination.
4. Treat any container mounting
   `enterprise-ai-workbench_postgres_data` as legacy-source-only. Never start
   it when its inspected image is Debian/Trixie or otherwise differs from the
   original `postgres:17.11-alpine3.24` image.
5. Confirm both named volumes independently with `docker volume inspect`.
   Neither inspection nor later container recreation may remove either volume.

If a stale container must be removed to proceed, first verify that it is
stopped and that its named backing volume is the preserved legacy volume. Use
only `docker rm <container-id>` without `--volumes`/`-v`, then immediately
re-run `docker volume inspect enterprise-ai-workbench_postgres_data`. Do not
use `docker compose down`, `--remove-orphans`, or any bulk removal command for
this step. Removing the legacy volume is never permitted.

## Preconditions

1. Preserve the stale-container preflight record, source image ID, PostgreSQL
   version, database list, Alembic revision, and both source and target volume
   names.
2. Resolve the exact source volume and verify it is
   `enterprise-ai-workbench_postgres_data` before any command that mounts it.
3. Create a separate host backup directory with sufficient free space and
   restrict access because dumps contain application data and database roles.
4. Stop every application process that can write to PostgreSQL. Keep only a
   source PostgreSQL container whose inspected image is the original
   `postgres:17.11-alpine3.24` image available for the logical dump; do not
   change the image attached to its volume. If no verified Alpine source is
   running, stop and obtain explicit approval for a source-recovery plan rather
   than starting a stale container.

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
2. Re-render and inspect `docker compose config`. Create the target from the
   current definition with:

   ```text
   docker compose up --detach --force-recreate --no-deps postgres_pgvector
   ```

   Do not substitute `docker compose start`. Force recreation reconciles the
   container with the reviewed image and mount definition while preserving
   named volumes.
3. Inspect the created `postgres_pgvector` container before restore. Confirm
   its image is `pgvector/pgvector:0.8.6-pg17-trixie`, its only data mount at
   `/var/lib/postgresql/data` is
   `enterprise-ai-workbench_postgres_pgvector_data`, and the legacy volume is
   not mounted anywhere in the container.
4. Confirm PostgreSQL major version 17 and that the server is healthy.
5. Restore required globals/roles, create the target databases, and restore
   each custom-format dump with `pg_restore --exit-on-error`.
6. Run Alembic upgrade to the approved head only after the restored revision
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
attached when the logical backup was taken. Inspect its image and mounts again
before starting it; never use the stale Debian/legacy-volume container as the
rollback source. Re-run source health and row-count checks before resuming the
application.

The legacy volume remains the rollback source until a later, separately
approved retention decision. Removal is never part of this runbook.
