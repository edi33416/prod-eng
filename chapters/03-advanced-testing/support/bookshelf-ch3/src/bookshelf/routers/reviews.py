from fastapi import APIRouter, HTTPException

from bookshelf import services
from bookshelf.database import get_connection
from bookshelf.models import ReviewCreate, ReviewResponse

router = APIRouter(tags=["reviews"])


@router.post("/books/{book_id}/reviews", response_model=ReviewResponse, status_code=201)
def add_review_endpoint(book_id: int, review: ReviewCreate) -> ReviewResponse:
    with get_connection() as conn:
        result = services.add_review(conn, book_id, review)
        if result is None:
            raise HTTPException(status_code=404, detail="Book not found")
        return result


@router.get("/books/{book_id}/reviews", response_model=list[ReviewResponse])
def list_reviews_endpoint(book_id: int) -> list[ReviewResponse]:
    with get_connection() as conn:
        reviews = services.list_reviews(conn, book_id)
        if reviews is None:
            raise HTTPException(status_code=404, detail="Book not found")
        return reviews
