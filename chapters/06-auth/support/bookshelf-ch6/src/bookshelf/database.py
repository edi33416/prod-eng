import os
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    false,
)
from sqlalchemy.engine import Connection, Engine

DEFAULT_DATABASE_URL = "sqlite:///bookshelf.db"

metadata = MetaData()

books = Table(
    "books",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", Text, nullable=False),
    Column("author", Text, nullable=False),
    Column("isbn", String(13), nullable=False, unique=True),
    Column("year", Integer, nullable=False),
)

reviews = Table(
    "reviews",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "book_id",
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("rating", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("reviewer", Text, nullable=False),
    CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    # NULL for accounts that only ever log in through GitHub.
    Column("password_hash", Text, nullable=True),
    Column("role", String(16), nullable=False, server_default="user"),
    Column("github_id", BigInteger, nullable=True, unique=True),
    Column("email", Text, nullable=True),
    CheckConstraint("role IN ('user', 'admin')", name="role_valid"),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # SHA-256 of the token. The token itself is never stored.
    Column("token_hash", String(64), nullable=False, unique=True),
    # Unix timestamps: portable across SQLite and PostgreSQL.
    Column("expires_at", BigInteger, nullable=False),
    Column("revoked", Boolean, nullable=False, server_default=false()),
)


def normalize_database_url(url: str) -> str:
    """Map generic PostgreSQL URLs onto the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _enable_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
    dbapi_conn.execute("PRAGMA foreign_keys = ON")


def make_engine(url: str) -> Engine:
    url = normalize_database_url(url)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        return engine
    return create_engine(url, pool_pre_ping=True)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    return _engine


def reset_engine() -> None:
    """Drop the cached engine so the next call re-reads DATABASE_URL."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_connection() -> Connection:
    return get_engine().connect()


def _create_schema(conn: Connection) -> None:
    metadata.create_all(conn)
    conn.commit()


def init_db() -> None:
    with get_connection() as conn:
        _create_schema(conn)
