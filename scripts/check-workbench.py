"""Read-only local startup preflight; never expose configuration or SQL errors."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root / "backend"))
    try:
        from alembic.script import ScriptDirectory
        from app.core.config import Settings
        from sqlalchemy import create_engine, text

        settings = Settings(_env_file=root / ".env")
        heads = set(ScriptDirectory(str(root / "backend" / "alembic")).get_heads())
    except Exception:  # noqa: BLE001 - CLI boundary must not print configuration/secret input.
        print("Configuration/dependencies invalid. Check .env and backend environment.")
        return 2
    try:
        with create_engine(settings.database_url, connect_args={"connect_timeout": 5}).connect() as db:
            revisions = set(db.execute(text("SELECT version_num FROM alembic_version")).scalars())
    except Exception:  # noqa: BLE001 - SQL exception text can contain database credentials.
        print("Database unavailable. Check the configured database connection.")
        return 3
    if revisions != heads:
        print("Database schema differs from this checkout. Review migrations manually.")
        return 4
    print("Database connection and migration revision OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
