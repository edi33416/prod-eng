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
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> CurrentUser:
    """Verify signature, expiry, issuer and audience.

    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        # A fixed list: never trust the "alg" field of the token itself.
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "exp", "iat", "iss", "aud"]},
    )
    try:
        return CurrentUser(
            id=int(payload["sub"]),
            username=str(payload["username"]),
            role=str(payload["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("Malformed claims") from exc


def new_refresh_token() -> tuple[str, str]:
    """Return (token, sha256 hex digest). Only the digest is stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
