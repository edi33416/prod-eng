import sqlite3

from fastapi import APIRouter, HTTPException

from bookshelf.database import get_connection
from bookshelf.models import ReviewCreate, ReviewResponse

router = APIRouter(tags=["reviews"])


def _require_book(conn: sqlite3.Connection, book_id: int) -> None:
    # TODO: Query the books table. Raise 404 if the book does not exist.
    raise NotImplementedError


# TODO: Implement POST /books/{book_id}/reviews — verify the book exists, insert the review,
#       return 201 with the created ReviewResponse.
@router.post("/books/{book_id}/reviews", response_model=ReviewResponse, status_code=201)
def add_review(book_id: int, review: ReviewCreate) -> ReviewResponse:
    raise NotImplementedError


# TODO: Implement GET /books/{book_id}/reviews — verify the book exists, return all reviews.
@router.get("/books/{book_id}/reviews", response_model=list[ReviewResponse])
def list_reviews(book_id: int) -> list[ReviewResponse]:
    raise NotImplementedError
