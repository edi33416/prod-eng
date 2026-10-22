from fastapi import APIRouter, HTTPException, Query

from bookshelf import services
from bookshelf.database import get_connection
from bookshelf.models import BookCreate, BookResponse, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])


@router.post("/", response_model=BookResponse, status_code=201)
def create_book_endpoint(book: BookCreate) -> BookResponse:
    with get_connection() as conn:
        try:
            return services.create_book(conn, book)
        except Exception:
            raise HTTPException(status_code=409, detail="A book with this ISBN already exists")


@router.get("/search", response_model=list[BookResponse])
def search_books_endpoint(
    q: str = Query(min_length=1, description="Search query for title or author"),
) -> list[BookResponse]:
    with get_connection() as conn:
        return services.search_books(conn, q)


@router.get("/top", response_model=list[BookResponse])
def top_books_endpoint(
    n: int = Query(default=5, ge=1, le=50, description="Number of top-rated books to return"),
) -> list[BookResponse]:
    with get_connection() as conn:
        return services.get_top_books(conn, n)


@router.get("/", response_model=list[BookResponse])
def list_books_endpoint(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[BookResponse]:
    with get_connection() as conn:
        return services.list_books(conn, offset, limit)


@router.get("/{book_id}", response_model=BookResponse)
def get_book_endpoint(book_id: int) -> BookResponse:
    with get_connection() as conn:
        book = services.get_book(conn, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")
        return book


@router.put("/{book_id}", response_model=BookResponse)
def update_book_endpoint(book_id: int, updates: BookUpdate) -> BookResponse:
    with get_connection() as conn:
        book = services.update_book(conn, book_id, updates)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")
        return book


@router.delete("/{book_id}", status_code=204)
def delete_book_endpoint(book_id: int) -> None:
    with get_connection() as conn:
        if not services.delete_book(conn, book_id):
            raise HTTPException(status_code=404, detail="Book not found")
