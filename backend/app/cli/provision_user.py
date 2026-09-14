import argparse
from getpass import getpass

from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.models import User
from app.security.passwords import hash_password


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision one development user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    email = arguments.email.strip().lower()
    name = arguments.name.strip()
    if not email or not name:
        raise SystemExit("Email and name must not be empty")

    with get_session_factory()() as session:
        user = session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.password_hash is not None:
            raise SystemExit("User already has a password and cannot be provisioned")

        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
        if not password:
            raise SystemExit("Password must not be empty")
        if password != confirmation:
            raise SystemExit("Passwords do not match")

        if user is None:
            user = User(email=email, name=name)
            session.add(user)
        user.password_hash = hash_password(password)
        session.commit()

    print(f"Provisioned development user {email}")


if __name__ == "__main__":
    main()
