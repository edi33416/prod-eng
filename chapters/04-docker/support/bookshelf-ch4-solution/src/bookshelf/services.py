from sqlalchemy import text
from sqlalchemy.engine import Connection

from bookshelf.models import (
    BookCreate,
    BookResponse,
    BookUpdate,
    ReviewCreate,
    ReviewResponse,
)


def validate_isbn(isbn: str) -> bool:
    digits = isbn.replace("-", "").replace(" ", "")
    return len(digits) in (10, 13) and digits.isdigit()


def calculate_average_rating(ratings: list[int]) -> float | None:
    if not ratings:
        return None
    return sum(ratings) / len(ratings)


def create_book(conn: Connection, book: BookCreate) -> BookResponse:
    row = conn.execute(
        text(
            "INSERT INTO books (title, author, isbn, year) "
            "VALUES (:title, :author, :isbn, :year) "
            "RETURNING id, title, author, isbn, year"
        ),
        book.model_dump(),
    ).mappings().one()
    conn.commit()
    return BookResponse(**row)


def get_book(conn: Connection, book_id: int) -> BookResponse | None:
    row = conn.execute(
        text("SELECT * FROM books WHERE id = :id"), {"id": book_id}
    ).mappings().first()
    return BookResponse(**row) if row else None


def list_books(
    conn: Connection, offset: int = 0, limit: int = 20
) -> list[BookResponse]:
    rows = conn.execute(
        text("SELECT * FROM books ORDER BY id LIMIT :limit OFFSET :offset"),
        {"limit": limit, "offset": offset},
    ).mappings().all()
    return [BookResponse(**row) for row in rows]


def update_book(
    conn: Connection, book_id: int, updates: BookUpdate
) -> BookResponse | None:
    _UPDATABLE = {"title", "author", "isbn", "year"}
    fields = {
        k: v for k, v in updates.model_dump().items() if v is not None and k in _UPDATABLE
    }
    if not fields:
        return get_book(conn, book_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    result = conn.execute(
        text(f"UPDATE books SET {set_clause} WHERE id = :id"),  # noqa: S608
        {**fields, "id": book_id},
    )
    conn.commit()
    return get_book(conn, book_id) if result.rowcount > 0 else None


def delete_book(conn: Connection, book_id: int) -> bool:
    result = conn.execute(text("DELETE FROM books WHERE id = :id"), {"id": book_id})
    conn.commit()
    return result.rowcount > 0


def search_books(conn: Connection, query: str) -> list[BookResponse]:
    # LIKE is case-insensitive in SQLite but case-sensitive in PostgreSQL.
    # Lower-casing both sides gives the same behaviour on both engines.
    rows = conn.execute(
        text(
            "SELECT * FROM books "
            "WHERE LOWER(title) LIKE :pattern OR LOWER(author) LIKE :pattern "
            "ORDER BY id"
        ),
        {"pattern": f"%{query.lower()}%"},
    ).mappings().all()
    return [BookResponse(**row) for row in rows]


def get_top_books(conn: Connection, n: int) -> list[BookResponse]:
    if n <= 0:
        return []
    rows = conn.execute(
        text(
            """
            SELECT b.id, b.title, b.author, b.isbn, b.year
            FROM books b
            LEFT JOIN reviews r ON b.id = r.book_id
            GROUP BY b.id, b.title, b.author, b.isbn, b.year
            ORDER BY COALESCE(AVG(r.rating), 0) DESC, b.id
            LIMIT :n
            """
        ),
        {"n": n},
    ).mappings().all()
    return [BookResponse(**row) for row in rows]


def add_review(
    conn: Connection, book_id: int, review: ReviewCreate
) -> ReviewResponse | None:
    if get_book(conn, book_id) is None:
        return None
    row = conn.execute(
        text(
            "INSERT INTO reviews (book_id, rating, text, reviewer) "
            "VALUES (:book_id, :rating, :text, :reviewer) "
            "RETURNING id, book_id, rating, text, reviewer"
        ),
        {"book_id": book_id, **review.model_dump()},
    ).mappings().one()
    conn.commit()
    return ReviewResponse(**row)


def list_reviews(conn: Connection, book_id: int) -> list[ReviewResponse] | None:
    if get_book(conn, book_id) is None:
        return None
    rows = conn.execute(
        text("SELECT * FROM reviews WHERE book_id = :book_id ORDER BY id"),
        {"book_id": book_id},
    ).mappings().all()
    return [ReviewResponse(**row) for row in rows]
