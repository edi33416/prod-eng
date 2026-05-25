import sqlite3

from bookshelf.models import BookCreate, BookResponse, BookUpdate, ReviewCreate, ReviewResponse


def validate_isbn(isbn: str) -> bool:
    # TODO: Strip hyphens and spaces, then check that the length is 10 or 13 digits.
    raise NotImplementedError


def calculate_average_rating(ratings: list[int]) -> float | None:
    # TODO: Return None for an empty list; otherwise return the mean.
    raise NotImplementedError


def create_book(conn: sqlite3.Connection, book: BookCreate) -> BookResponse:
    # TODO: INSERT the book into the database and return the created BookResponse.
    raise NotImplementedError


def get_book(conn: sqlite3.Connection, book_id: int) -> BookResponse | None:
    # TODO: SELECT the book by id. Return None if not found.
    raise NotImplementedError


def list_books(
    conn: sqlite3.Connection, offset: int = 0, limit: int = 20
) -> list[BookResponse]:
    # TODO: SELECT books with LIMIT/OFFSET pagination.
    raise NotImplementedError


def update_book(
    conn: sqlite3.Connection, book_id: int, updates: BookUpdate
) -> BookResponse | None:
    # TODO: UPDATE only the non-None fields in 'updates'. Return None if book_id not found.
    raise NotImplementedError


def delete_book(conn: sqlite3.Connection, book_id: int) -> bool:
    # TODO: DELETE the book. Return True if a row was deleted, False if not found.
    raise NotImplementedError


def search_books(conn: sqlite3.Connection, query: str) -> list[BookResponse]:
    # TODO: SELECT books WHERE title LIKE %query% OR author LIKE %query%.
    raise NotImplementedError


def get_top_books(conn: sqlite3.Connection, n: int) -> list[BookResponse]:
    # TODO: Return the top n books ordered by average rating DESC.
    #       Books with no reviews should appear last (average = 0).
    #       Return [] if n <= 0.
    raise NotImplementedError


def add_review(
    conn: sqlite3.Connection, book_id: int, review: ReviewCreate
) -> ReviewResponse | None:
    # TODO: Verify the book exists (return None if not). INSERT the review.
    raise NotImplementedError


def list_reviews(
    conn: sqlite3.Connection, book_id: int
) -> list[ReviewResponse] | None:
    # TODO: Verify the book exists (return None if not). SELECT all reviews for the book.
    raise NotImplementedError
