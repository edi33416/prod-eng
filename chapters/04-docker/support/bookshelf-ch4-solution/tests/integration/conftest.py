import itertools
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from bookshelf.main import app


@pytest.fixture
def client(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Point the app at the per-test database instead of DATABASE_URL.
    monkeypatch.setattr("bookshelf.database._engine", db_engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def create_book(client: TestClient):  # type: ignore[type-arg]
    counter = itertools.count(1)

    def _create(**overrides: object) -> dict:  # type: ignore[type-arg]
        defaults: dict[str, object] = {
            "title": "Test Book",
            "author": "Test Author",
            "isbn": f"978{next(counter):010d}",
            "year": 2020,
        }
        defaults.update(overrides)
        response = client.post("/books/", json=defaults)
        assert response.status_code == 201, response.json()
        return response.json()  # type: ignore[no-any-return]

    return _create
