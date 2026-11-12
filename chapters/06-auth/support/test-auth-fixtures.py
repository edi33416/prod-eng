"""Reference pytest fixtures for testing authenticated FastAPI endpoints.

Copy what you need into tests/integration/conftest.py. The complete,
working version is in bookshelf-ch6-solution/tests/integration/conftest.py.

The idea: mint tokens directly with the application's own
create_access_token(). The login flow is tested once, in its own tests;
every other test should not pay for (or depend on) registration, password
hashing and /auth/login.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from bookshelf.auth.config import get_settings
from bookshelf.auth.dependencies import get_current_user
from bookshelf.auth.rate_limit import login_rate_limit
from bookshelf.auth.tokens import CurrentUser, create_access_token
from bookshelf.main import app

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"  # noqa: S105

TokenFactory = Callable[..., str]


# -- Configuration: belongs in the ROOT tests/conftest.py --------------------


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A known secret for every test, and no state leaking between tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()  # settings are cached; re-read the env
    login_rate_limit.reset()  # in-memory counters survive between tests
    yield
    get_settings.cache_clear()


# -- Strategy 1: real tokens, minted directly --------------------------------


@pytest.fixture
def make_token() -> TokenFactory:
    def _make(
        user_id: int = 1,
        username: str = "test-user",
        role: str = "user",
        expires_delta: timedelta | None = None,
    ) -> str:
        return create_access_token(
            CurrentUser(id=user_id, username=username, role=role), expires_delta
        )

    return _make


@pytest.fixture
def auth_headers(make_token: TokenFactory) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def admin_headers(make_token: TokenFactory) -> dict[str, str]:
    token = make_token(user_id=2, username="test-admin", role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def expired_headers(make_token: TokenFactory) -> dict[str, str]:
    token = make_token(expires_delta=timedelta(seconds=-1))
    return {"Authorization": f"Bearer {token}"}


# -- Strategy 2: skip token handling entirely --------------------------------


@pytest.fixture
def as_admin() -> Iterator[None]:
    """Replace get_current_user for the duration of one test.

    Fast and simple, but the token code does not run at all: a bug in
    decode_access_token would go unnoticed. Use it for tests that are about
    something else, never for tests about auth.
    """
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=2, username="test-admin", role="admin"
    )
    yield
    app.dependency_overrides.clear()


# -- Usage --------------------------------------------------------------------


def test_delete_requires_admin(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.delete("/books/1", headers=auth_headers).status_code == 403


def test_expired_token(client: TestClient, expired_headers: dict[str, str]) -> None:
    response = client.post("/books/", json={}, headers=expired_headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Token expired"
