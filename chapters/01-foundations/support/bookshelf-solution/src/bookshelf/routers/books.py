from fastapi import APIRouter, HTTPException, Query

from bookshelf.database import get_connection
from bookshelf.models import BookCreate, BookResponse, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])

_UPDATABLE_FIELDS = {"title", "author", "isbn", "year"}


@router.post("/", response_model=BookResponse, status_code=201)
def create_book(book: BookCreate) -> BookResponse:
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
                (book.title, book.author, book.isbn, book.year),
            )
            conn.commit()
        except Exception:
            raise HTTPException(status_code=409, detail="A book with this ISBN already exists")
        row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return BookResponse(**dict(row))


@router.get("/search", response_model=list[BookResponse])
def search_books(
    q: str = Query(min_length=1, description="Search query for title or author"),
) -> list[BookResponse]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        return [BookResponse(**dict(row)) for row in rows]


@router.get("/", response_model=list[BookResponse])
def list_books(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[BookResponse]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM books LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [BookResponse(**dict(row)) for row in rows]


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int) -> BookResponse:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Book not found")
        return BookResponse(**dict(row))


@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: int, updates: BookUpdate) -> BookResponse:
    fields = {
        k: v
        for k, v in updates.model_dump().items()
        if v is not None and k in _UPDATABLE_FIELDS
    }
    if not fields:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [book_id]
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE books SET {set_clause} WHERE id = ?", values  # noqa: S608
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Book not found")
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return BookResponse(**dict(row))


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Book not found")
