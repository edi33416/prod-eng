import pytest
from sqlalchemy.engine import Connection

from bookshelf import database, services
from bookshelf.models import BookCreate


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgresql://bookshelf:secret@db:5432/bookshelf",
            "postgresql+psycopg://bookshelf:secret@db:5432/bookshelf",
        ),
        (
            "postgres://bookshelf:secret@db:5432/bookshelf",
            "postgresql+psycopg://bookshelf:secret@db:5432/bookshelf",
        ),
        (
            "postgresql+psycopg://bookshelf:secret@db/bookshelf",
            "postgresql+psycopg://bookshelf:secret@db/bookshelf",
        ),
        ("sqlite:///bookshelf.db", "sqlite:///bookshelf.db"),
    ],
)
def test_normalize_database_url(url: str, expected: str) -> None:
    assert database.normalize_database_url(url) == expected


def test_get_engine_reads_database_url(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "from-env.db"  # type: ignore[operator]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    database.reset_engine()
    try:
        assert database.get_engine().url.database == str(db_file)
    finally:
        database.reset_engine()


def test_get_engine_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database.reset_engine()
    try:
        assert database.get_engine().dialect.name == "sqlite"
    finally:
        database.reset_engine()


def test_search_is_case_insensitive(db_conn: Connection) -> None:
    # SQLite's LIKE ignores case; PostgreSQL's does not. This test pins the
    # behaviour so it holds on both engines.
    services.create_book(
        db_conn,
        BookCreate(
            title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
        ),
    )
    assert len(services.search_books(db_conn, "clean")) == 1
    assert len(services.search_books(db_conn, "ROBERT")) == 1
