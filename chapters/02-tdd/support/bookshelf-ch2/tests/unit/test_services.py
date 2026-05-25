import sqlite3

import pytest

from bookshelf import services
from bookshelf.models import BookCreate, ReviewCreate


# ---------------------------------------------------------------------------
# calculate_average_rating
# ---------------------------------------------------------------------------

def test_average_rating_no_reviews() -> None:
    # TODO: Call services.calculate_average_rating([]) and assert the result is None.
    raise NotImplementedError


def test_average_rating_single_review() -> None:
    # TODO: Assert calculate_average_rating([4]) == 4.0
    raise NotImplementedError


def test_average_rating_multiple_reviews() -> None:
    # TODO: Assert calculate_average_rating([5, 3, 4]) == 4.0
    raise NotImplementedError


# ---------------------------------------------------------------------------
# create_book / get_book
# ---------------------------------------------------------------------------

def test_create_book_returns_response_with_id(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    # TODO: Call services.create_book, assert id is set and fields match.
    raise NotImplementedError


def test_get_book_returns_correct_data(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    # TODO: Create a book, then get it by id. Assert fields match.
    raise NotImplementedError


def test_get_book_not_found_returns_none(db_conn: sqlite3.Connection) -> None:
    # TODO: Assert services.get_book(db_conn, 999) is None
    raise NotImplementedError


# ---------------------------------------------------------------------------
# search_books
# ---------------------------------------------------------------------------

def test_search_books_by_title(populated_db: sqlite3.Connection) -> None:
    # TODO: Search for "Clean", assert exactly one result with title "Clean Code".
    raise NotImplementedError


def test_search_books_no_results(populated_db: sqlite3.Connection) -> None:
    # TODO: Search for "Kubernetes", assert empty list.
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Add more tests as you implement each service function.
# See bookshelf-ch2-solution/tests/ for the full reference test suite.
# ---------------------------------------------------------------------------
