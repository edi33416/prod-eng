import sqlite3

from fastapi import APIRouter, HTTPException

from bookshelf.database import get_connection
from bookshelf.models import ReviewCreate, ReviewResponse

router = APIRouter(tags=["reviews"])


def _require_book(conn: sqlite3.Connection, book_id: int) -> None:
    row = conn.execute("SELECT id FROM books WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")


@router.post("/books/{book_id}/reviews", response_model=ReviewResponse, status_code=201)
def add_review(book_id: int, review: ReviewCreate) -> ReviewResponse:
    with get_connection() as conn:
        _require_book(conn, book_id)
        cursor = conn.execute(
            "INSERT INTO reviews (book_id, rating, text, reviewer) VALUES (?, ?, ?, ?)",
            (book_id, review.rating, review.text, review.reviewer),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return ReviewResponse(**dict(row))


@router.get("/books/{book_id}/reviews", response_model=list[ReviewResponse])
def list_reviews(book_id: int) -> list[ReviewResponse]:
    with get_connection() as conn:
        _require_book(conn, book_id)
        rows = conn.execute(
            "SELECT * FROM reviews WHERE book_id = ?", (book_id,)
        ).fetchall()
        return [ReviewResponse(**dict(row)) for row in rows]
