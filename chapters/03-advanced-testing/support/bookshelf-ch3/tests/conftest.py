import sqlite3

import pytest

from bookshelf import services
from bookshelf.database import _create_schema
from bookshelf.models import BookCreate, ReviewCreate


@pytest.fixture
def db_conn(tmp_path: pytest.TempPathFactory) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _create_schema(conn)
    yield conn  # type: ignore[misc]
    conn.close()


@pytest.fixture
def sample_book() -> BookCreate:
    return BookCreate(
        title="The Pragmatic Programmer",
        author="David Thomas",
        isbn="9780135957059",
        year=1999,
    )


@pytest.fixture
def sample_books() -> list[BookCreate]:
    return [
        BookCreate(title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008),
        BookCreate(title="Design Patterns", author="Gang of Four", isbn="9780201633610", year=1994),
        BookCreate(title="The Pragmatic Programmer", author="David Thomas", isbn="9780135957059", year=1999),
        BookCreate(title="Refactoring", author="Martin Fowler", isbn="9780201485677", year=1999),
        BookCreate(
            title="Working Effectively with Legacy Code",
            author="Michael Feathers",
            isbn="9780131177055",
            year=2004,
        ),
    ]


@pytest.fixture
def populated_db(db_conn: sqlite3.Connection, sample_books: list[BookCreate]) -> sqlite3.Connection:
    for book in sample_books:
        services.create_book(db_conn, book)
    services.add_review(db_conn, 1, ReviewCreate(rating=5, text="Essential.", reviewer="alice"))
    services.add_review(db_conn, 1, ReviewCreate(rating=4, text="Very good.", reviewer="bob"))
    services.add_review(db_conn, 2, ReviewCreate(rating=3, text="Decent.", reviewer="alice"))
    services.add_review(db_conn, 3, ReviewCreate(rating=5, text="Classic.", reviewer="carol"))
    return db_conn
