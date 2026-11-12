import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from bookshelf.auth.config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str


def create_access_token(
    user: CurrentUser, expires_delta: timedelta | None = None
) -> str:
    # TODO(ch6): Build the claims (sub, username, role, iss, aud, iat, exp)
    # and sign them with settings.jwt_secret_key using HS256.
    raise NotImplementedError


def decode_access_token(token: str) -> CurrentUser:
    """Verify signature, expiry, issuer and audience.

    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError.
    """
    # TODO(ch6): jwt.decode with a FIXED algorithms list, issuer, audience
    # and required claims; turn the payload into a CurrentUser.
    raise NotImplementedError


def new_refresh_token() -> tuple[str, str]:
    """Return (token, sha256 hex digest). Only the digest is stored."""
    # TODO(ch6): Random, URL-safe, at least 32 bytes (secrets module).
    raise NotImplementedError


def hash_refresh_token(token: str) -> str:
    # TODO(ch6): SHA-256 hex digest.
    raise NotImplementedError
