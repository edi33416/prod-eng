from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Argon2id with pwdlib's defaults (OWASP-recommended parameters). The
# parameters are stored inside every hash, so they can be raised later
# without invalidating existing passwords.
_hasher = PasswordHash((Argon2Hasher(),))

# Compared against when the username does not exist, so that a failed login
# takes the same time whether or not the account exists.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)
