from pathlib import Path

from app.core.config import ENV_FILE


def test_env_file_is_resolved_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert ENV_FILE == repository_root / ".env"
