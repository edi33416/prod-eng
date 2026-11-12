import itertools
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from bookshelf.auth.tokens import CurrentUser, create_access_token
from bookshelf.main import app

TokenFactory = Callable[..., str]


@pytest.fixture
def client(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An anonymous client: no Authorization header."""
    # Point the app at the per-test database instead of DATABASE_URL.
    monkeypatch.setattr("bookshelf.database._engine", db_engine)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Authentication: mint tokens directly instead of going through /auth/login.
# The login flow itself is tested once, in test_auth_api.py.
# ---------------------------------------------------------------------------


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
def auth_client(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    """The same client, sending a "user" token with every request."""
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def admin_client(client: TestClient, admin_headers: dict[str, str]) -> TestClient:
    """The same client, sending an "admin" token with every request."""
    client.headers.update(admin_headers)
    return client


@pytest.fixture
def create_book(client: TestClient, auth_headers: dict[str, str]):  # type: ignore[type-arg]
    counter = itertools.count(1)

    def _create(**overrides: object) -> dict:  # type: ignore[type-arg]
        defaults: dict[str, object] = {
            "title": "Test Book",
            "author": "Test Author",
            "isbn": f"978{next(counter):010d}",
            "year": 2020,
        }
        defaults.update(overrides)
        response = client.post("/books/", json=defaults, headers=auth_headers)
        assert response.status_code == 201, response.json()
        return response.json()  # type: ignore[no-any-return]

    return _create
