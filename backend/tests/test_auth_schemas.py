import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest


def test_login_request_normalizes_email_and_redacts_password() -> None:
    request = LoginRequest(email=" Alice@Company.com ", password="private-password")

    assert request.email == "alice@company.com"
    assert request.password.get_secret_value() == "private-password"
    assert "private-password" not in repr(request)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "alice@company.com", "password": ""},
        {"email": " ", "password": "password"},
        {"email": "alice@company.com", "password": "password", "role": "admin"},
    ],
)
def test_login_request_rejects_invalid_bodies(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(payload)
