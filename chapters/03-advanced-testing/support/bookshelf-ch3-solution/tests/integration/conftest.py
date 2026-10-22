import itertools

import pytest
from fastapi.testclient import TestClient

from bookshelf.database import init_db
from bookshelf.main import app


@pytest.fixture
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test.db"  # type: ignore[operator]
    monkeypatch.setattr("bookshelf.database.DB_PATH", db_path)
    init_db()
    with TestClient(app) as c:
        yield c  # type: ignore[misc]


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
