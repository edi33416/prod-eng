import pytest

from bookshelf.auth.config import ConfigError, get_settings


def test_missing_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY")
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="JWT_SECRET_KEY"):
        get_settings()


def test_short_secret_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "secret")
    get_settings.cache_clear()
    with pytest.raises(ConfigError):
        get_settings()


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COOKIE_SECURE")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.access_token_minutes == 15
    assert settings.refresh_token_days == 7
    assert settings.cookie_secure is True
