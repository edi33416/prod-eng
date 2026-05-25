import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bookshelf.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    # TODO: Create the 'books' and 'reviews' tables using CREATE TABLE IF NOT EXISTS.
    # books:   id, title, author, isbn (UNIQUE), year
    # reviews: id, book_id (FK -> books.id ON DELETE CASCADE), rating (CHECK 1-5), text, reviewer
    raise NotImplementedError
