import pytest
from sqlalchemy.engine import make_url

from tests.integration.safety import assert_safe_test_database


def test_database_reset_rejects_runtime_database() -> None:
    database_url = make_url("postgresql+psycopg://workbench:secret@localhost/workbench")

    with pytest.raises(RuntimeError, match="must differ"):
        assert_safe_test_database(database_url, database_url)


def test_database_reset_requires_test_suffix() -> None:
    database_url = make_url("postgresql+psycopg://workbench:secret@localhost/workbench")
    unsafe_test_url = make_url("postgresql+psycopg://workbench:secret@localhost/other")

    with pytest.raises(RuntimeError, match="must end with '_test'"):
        assert_safe_test_database(database_url, unsafe_test_url)


def test_database_reset_accepts_distinct_test_database() -> None:
    database_url = make_url("postgresql+psycopg://workbench:secret@localhost/workbench")
    test_database_url = make_url(
        "postgresql+psycopg://workbench:secret@localhost/workbench_test"
    )

    assert_safe_test_database(database_url, test_database_url)
