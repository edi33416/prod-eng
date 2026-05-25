import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bookshelf.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                title  TEXT    NOT NULL,
                author TEXT    NOT NULL,
                isbn   TEXT    NOT NULL UNIQUE,
                year   INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id  INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                rating   INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                text     TEXT    NOT NULL,
                reviewer TEXT    NOT NULL
            )
        """)
        conn.commit()
