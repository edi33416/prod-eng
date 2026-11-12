from bookshelf.auth.passwords import hash_password, verify_password


def test_hash_is_not_the_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse" not in hashed
    assert hashed.startswith("$argon2id$")


def test_same_password_hashes_differently() -> None:
    # A random salt per hash: equal passwords do not produce equal hashes.
    assert hash_password("same password!") != hash_password("same password!")


def test_verify_correct_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("Correct horse battery staple", hashed) is False


def test_verify_without_hash_returns_false() -> None:
    assert verify_password("anything at all", None) is False
