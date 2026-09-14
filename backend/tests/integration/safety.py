from sqlalchemy.engine import URL


def assert_safe_test_database(database_url: URL, test_database_url: URL) -> None:
    if test_database_url == database_url:
        raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL")
    if not test_database_url.database or not test_database_url.database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database name must end with '_test'")
