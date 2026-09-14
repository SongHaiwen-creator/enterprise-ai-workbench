from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from tests.integration.safety import assert_safe_test_database

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_urls() -> tuple[URL, URL]:
    try:
        settings = get_settings()
    except ValidationError:
        pytest.skip("PostgreSQL integration tests require repository-root .env settings")

    if settings.test_database_url is None:
        pytest.skip("PostgreSQL integration tests require TEST_DATABASE_URL")

    database_url = make_url(settings.database_url)
    test_database_url = make_url(settings.test_database_url)
    assert_safe_test_database(database_url, test_database_url)
    return database_url, test_database_url


@pytest.fixture(scope="session")
def postgres_engine(database_urls: tuple[URL, URL]) -> Generator[Engine, None, None]:
    _, test_database_url = database_urls
    engine = create_engine(test_database_url, pool_pre_ping=True)

    # Both safety checks above must complete before this destructive reset.
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Generator[Session, None, None]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
