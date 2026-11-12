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
    # TODO(ch6): Hash with Argon2id via the module-level _hasher.
    raise NotImplementedError


def verify_password(password: str, password_hash: str | None) -> bool:
    # TODO(ch6): Return False for a None hash, but still spend the time
    # hashing (verify against _DUMMY_HASH) so unknown users are not faster.
    raise NotImplementedError
