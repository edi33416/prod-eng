import itertools
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Connection, Engine

# Read by bookshelf.main at import time, so it must be set before any test
# module imports the app.
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "https://bookshelf.example.com")

from bookshelf import services  # noqa: E402
from bookshelf.auth.config import get_settings  # noqa: E402
from bookshelf.auth.rate_limit import login_rate_limit  # noqa: E402
from bookshelf.database import make_engine, metadata  # noqa: E402
from bookshelf.models import (  # noqa: E402
    BookCreate,
    BookResponse,
    ReviewCreate,
    ReviewResponse,
)

TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"  # noqa: S105


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Known auth configuration for every test, and a clean rate limiter."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    # The test client talks plain HTTP; Secure cookies would never be sent.
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
    get_settings.cache_clear()
    login_rate_limit.reset()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    """A fresh, empty database per test.

    SQLite in a temp directory by default. Set TEST_DATABASE_URL to run the
    same tests against PostgreSQL (see docker-compose.test.yml).
    """
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    engine = make_engine(url)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_conn(db_engine: Engine) -> Iterator[Connection]:
    with db_engine.connect() as conn:
        yield conn


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
        BookCreate(
            title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
        ),
        BookCreate(
            title="Design Patterns",
            author="Gang of Four",
            isbn="9780201633610",
            year=1994,
        ),
        BookCreate(
            title="The Pragmatic Programmer",
            author="David Thomas",
            isbn="9780135957059",
            year=1999,
        ),
        BookCreate(
            title="Refactoring", author="Martin Fowler", isbn="9780201485677", year=1999
        ),
        BookCreate(
            title="Working Effectively with Legacy Code",
            author="Michael Feathers",
            isbn="9780131177055",
            year=2004,
        ),
    ]


@pytest.fixture
def populated_db(db_conn: Connection, sample_books: list[BookCreate]) -> Connection:
    for book in sample_books:
        services.create_book(db_conn, book)
    services.add_review(
        db_conn, 1, ReviewCreate(rating=5, text="Essential."), reviewer="alice"
    )
    services.add_review(
        db_conn, 1, ReviewCreate(rating=4, text="Very good."), reviewer="bob"
    )
    services.add_review(
        db_conn, 2, ReviewCreate(rating=3, text="Decent."), reviewer="alice"
    )
    services.add_review(
        db_conn, 3, ReviewCreate(rating=5, text="Classic."), reviewer="carol"
    )
    return db_conn


@pytest.fixture
def book_factory(db_conn: Connection):  # type: ignore[type-arg]
    counter = itertools.count(1)

    def _create(**overrides: object) -> BookResponse:
        defaults: dict[str, object] = {
            "title": "Test Book",
            "author": "Test Author",
            "isbn": f"978{next(counter):010d}",
            "year": 2020,
        }
        defaults.update(overrides)
        return services.create_book(db_conn, BookCreate(**defaults))  # type: ignore[arg-type]

    return _create


@pytest.fixture
def review_factory(db_conn: Connection):  # type: ignore[type-arg]
    def _create(book_id: int, **overrides: object) -> ReviewResponse | None:
        reviewer = str(overrides.pop("reviewer", "test_user"))
        defaults: dict[str, object] = {"rating": 5, "text": "Great book."}
        defaults.update(overrides)
        return services.add_review(
            db_conn,
            book_id,
            ReviewCreate(**defaults),  # type: ignore[arg-type]
            reviewer=reviewer,
        )

    return _create
