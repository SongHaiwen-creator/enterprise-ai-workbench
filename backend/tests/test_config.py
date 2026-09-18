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


def test_embedding_contract_has_fixed_mvp_defaults() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key="configuration-secret-longer-than-thirty-two-bytes",
        _env_file=None,
    )

    assert settings.openai_api_key is None
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536
    assert settings.openai_timeout_seconds == 30


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_model", "incompatible-model"),
        ("embedding_dimensions", 3072),
        ("openai_timeout_seconds", 0),
    ],
)
def test_embedding_contract_rejects_incompatible_configuration(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(
            database_url="postgresql+psycopg://unused/unused",
            jwt_secret_key="configuration-secret-longer-than-thirty-two-bytes",
            _env_file=None,
            **{field: value},
        )
