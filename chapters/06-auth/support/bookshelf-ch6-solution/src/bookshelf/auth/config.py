import os
from dataclasses import dataclass
from functools import lru_cache

MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """Raised at startup when auth configuration is missing or unsafe."""


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_issuer: str
    jwt_audience: str
    access_token_minutes: int
    refresh_token_days: int
    cookie_secure: bool
    github_client_id: str | None
    github_client_secret: str | None
    github_redirect_uri: str


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@lru_cache
def get_settings() -> AuthSettings:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise ConfigError(
            f"JWT_SECRET_KEY must be set to at least {MIN_SECRET_LENGTH} characters. "
            'Generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )
    return AuthSettings(
        jwt_secret_key=secret,
        jwt_algorithm="HS256",
        jwt_issuer="bookshelf",
        jwt_audience="bookshelf-api",
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        cookie_secure=_env_bool("COOKIE_SECURE", True),
        github_client_id=os.getenv("GITHUB_CLIENT_ID") or None,
        github_client_secret=os.getenv("GITHUB_CLIENT_SECRET") or None,
        github_redirect_uri=os.getenv(
            "GITHUB_REDIRECT_URI", "http://localhost:8000/auth/github/callback"
        ),
    )
