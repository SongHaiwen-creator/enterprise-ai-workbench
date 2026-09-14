from app.security.passwords import hash_password, verify_password


def test_password_is_hashed_with_argon2id_and_verifies() -> None:
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash)
    assert not verify_password("incorrect password", password_hash)


def test_password_hashes_use_distinct_salts() -> None:
    password = "same password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert verify_password(password, second_hash)


def test_malformed_password_hash_fails_verification() -> None:
    assert not verify_password("password", "not-an-argon2-hash")
