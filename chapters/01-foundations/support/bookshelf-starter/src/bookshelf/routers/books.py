from fastapi import APIRouter, HTTPException, Query

from bookshelf.database import get_connection
from bookshelf.models import BookCreate, BookResponse, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])


# TODO: Implement POST /books/ — insert a new book, return 201 with the created BookResponse.
#       Raise 409 if the ISBN already exists.
@router.post("/", response_model=BookResponse, status_code=201)
def create_book(book: BookCreate) -> BookResponse:
    raise NotImplementedError


# TODO: Implement GET /books/search?q= — search books where title OR author LIKE %q%.
#       Register this route BEFORE /{book_id} to avoid path matching conflicts.
@router.get("/search", response_model=list[BookResponse])
def search_books(
    q: str = Query(min_length=1, description="Search query for title or author"),
) -> list[BookResponse]:
    raise NotImplementedError


# TODO: Implement GET /books/ — list books with offset/limit pagination.
@router.get("/", response_model=list[BookResponse])
def list_books(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[BookResponse]:
    raise NotImplementedError


# TODO: Implement GET /books/{book_id} — return the book or raise 404.
@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int) -> BookResponse:
    raise NotImplementedError


# TODO: Implement PUT /books/{book_id} — update only the fields present in 'updates'.
#       Raise 404 if not found, 422 if no fields are provided.
@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: int, updates: BookUpdate) -> BookResponse:
    raise NotImplementedError


# TODO: Implement DELETE /books/{book_id} — delete the book (status 204) or raise 404.
@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int) -> None:
    raise NotImplementedError
