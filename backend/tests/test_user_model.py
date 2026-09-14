from app.models import User


def test_user_email_is_normalized_to_lowercase() -> None:
    user = User(email=" Alice@Company.com ", name="Alice")

    assert user.email == "alice@company.com"
