import sqlite3

from bookshelf.models import BookCreate, BookResponse, BookUpdate, ReviewCreate, ReviewResponse


def validate_isbn(isbn: str) -> bool:
    digits = isbn.replace("-", "").replace(" ", "")
    return len(digits) in (10, 13)


def calculate_average_rating(ratings: list[int]) -> float | None:
    if not ratings:
        return None
    return sum(ratings) / len(ratings)


def create_book(conn: sqlite3.Connection, book: BookCreate) -> BookResponse:
    cursor = conn.execute(
        "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
        (book.title, book.author, book.isbn, book.year),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return BookResponse(**dict(row))


def get_book(conn: sqlite3.Connection, book_id: int) -> BookResponse | None:
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return BookResponse(**dict(row)) if row else None


def list_books(
    conn: sqlite3.Connection, offset: int = 0, limit: int = 20
) -> list[BookResponse]:
    rows = conn.execute(
        "SELECT * FROM books LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [BookResponse(**dict(row)) for row in rows]


def update_book(
    conn: sqlite3.Connection, book_id: int, updates: BookUpdate
) -> BookResponse | None:
    _UPDATABLE = {"title", "author", "isbn", "year"}
    fields = {
        k: v for k, v in updates.model_dump().items() if v is not None and k in _UPDATABLE
    }
    if not fields:
        return get_book(conn, book_id)
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [book_id]
    cursor = conn.execute(
        f"UPDATE books SET {set_clause} WHERE id = ?", values  # noqa: S608
    )
    conn.commit()
    return get_book(conn, book_id) if cursor.rowcount > 0 else None


def delete_book(conn: sqlite3.Connection, book_id: int) -> bool:
    cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    return cursor.rowcount > 0


def search_books(conn: sqlite3.Connection, query: str) -> list[BookResponse]:
    rows = conn.execute(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
        (f"%{query}%", f"%{query}%"),
    ).fetchall()
    return [BookResponse(**dict(row)) for row in rows]


def get_top_books(conn: sqlite3.Connection, n: int) -> list[BookResponse]:
    if n <= 0:
        return []
    rows = conn.execute(
        """
        SELECT b.id, b.title, b.author, b.isbn, b.year
        FROM books b
        LEFT JOIN reviews r ON b.id = r.book_id
        GROUP BY b.id
        ORDER BY COALESCE(AVG(r.rating), 0) DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    return [BookResponse(**dict(row)) for row in rows]


def add_review(
    conn: sqlite3.Connection, book_id: int, review: ReviewCreate
) -> ReviewResponse | None:
    if get_book(conn, book_id) is None:
        return None
    cursor = conn.execute(
        "INSERT INTO reviews (book_id, rating, text, reviewer) VALUES (?, ?, ?, ?)",
        (book_id, review.rating, review.text, review.reviewer),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return ReviewResponse(**dict(row))


def list_reviews(
    conn: sqlite3.Connection, book_id: int
) -> list[ReviewResponse] | None:
    if get_book(conn, book_id) is None:
        return None
    rows = conn.execute(
        "SELECT * FROM reviews WHERE book_id = ?", (book_id,)
    ).fetchall()
    return [ReviewResponse(**dict(row)) for row in rows]
