from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    test_database_url: str | None = None
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: Literal[30] = 30
    openai_api_key: SecretStr | None = None
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    embedding_dimensions: Literal[1536] = 1536
    generation_model: Literal["gpt-5.6-terra"] = "gpt-5.6-terra"
    generation_reasoning_effort: Literal["low"] = "low"
    generation_prompt_version: Literal["grounded-answer-v1"] = "grounded-answer-v1"
    generation_retrieval_limit: Literal[5] = 5
    generation_max_input_tokens: Literal[12000] = 12000
    generation_max_output_tokens: Literal[1200] = 1200
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("openai_api_key")
    @classmethod
    def normalize_openai_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
