from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ENV_FILE, Settings


def test_env_file_is_resolved_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert ENV_FILE == repository_root / ".env"


def test_authentication_configuration_requires_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="jwt_secret_key"):
        Settings(
            database_url="postgresql+psycopg://unused/unused",
            _env_file=None,
        )


def test_authentication_configuration_rejects_a_short_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(
            database_url="postgresql+psycopg://unused/unused",
            jwt_secret_key="too-short",
            _env_file=None,
        )
