import sqlite3

import pytest

from bookshelf import services
from bookshelf.models import BookCreate, ReviewCreate


# ---------------------------------------------------------------------------
# calculate_average_rating
# ---------------------------------------------------------------------------

def test_average_rating_no_reviews() -> None:
    assert services.calculate_average_rating([]) is None


def test_average_rating_single_review() -> None:
    assert services.calculate_average_rating([4]) == 4.0


def test_average_rating_multiple_reviews() -> None:
    assert services.calculate_average_rating([5, 3, 4]) == 4.0


# ---------------------------------------------------------------------------
# create_book / get_book
# ---------------------------------------------------------------------------

def test_create_book_returns_response_with_id(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    result = services.create_book(db_conn, sample_book)
    assert result.id == 1
    assert result.title == sample_book.title
    assert result.isbn == sample_book.isbn


def test_create_book_duplicate_isbn_raises(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    services.create_book(db_conn, sample_book)
    with pytest.raises(Exception):
        services.create_book(db_conn, sample_book)


def test_get_book_returns_correct_data(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    created = services.create_book(db_conn, sample_book)
    result = services.get_book(db_conn, created.id)
    assert result is not None
    assert result.title == sample_book.title


def test_get_book_not_found_returns_none(db_conn: sqlite3.Connection) -> None:
    assert services.get_book(db_conn, 999) is None


# ---------------------------------------------------------------------------
# list_books
# ---------------------------------------------------------------------------

def test_list_books_empty_db(db_conn: sqlite3.Connection) -> None:
    assert services.list_books(db_conn) == []


def test_list_books_returns_all(
    db_conn: sqlite3.Connection, sample_books: list[BookCreate]
) -> None:
    for book in sample_books:
        services.create_book(db_conn, book)
    result = services.list_books(db_conn)
    assert len(result) == len(sample_books)


def test_list_books_pagination(
    db_conn: sqlite3.Connection, sample_books: list[BookCreate]
) -> None:
    for book in sample_books:
        services.create_book(db_conn, book)
    page_1 = services.list_books(db_conn, offset=0, limit=2)
    page_2 = services.list_books(db_conn, offset=2, limit=2)
    assert len(page_1) == 2
    assert len(page_2) == 2
    assert page_1[0].id != page_2[0].id


# ---------------------------------------------------------------------------
# search_books
# ---------------------------------------------------------------------------

def test_search_books_by_title(populated_db: sqlite3.Connection) -> None:
    results = services.search_books(populated_db, "Clean")
    assert len(results) == 1
    assert results[0].title == "Clean Code"


def test_search_books_by_author(populated_db: sqlite3.Connection) -> None:
    results = services.search_books(populated_db, "Gang of Four")
    assert len(results) == 1
    assert results[0].title == "Design Patterns"


def test_search_books_partial_match(populated_db: sqlite3.Connection) -> None:
    results = services.search_books(populated_db, "Prag")
    assert len(results) == 1
    assert results[0].title == "The Pragmatic Programmer"


def test_search_books_case_insensitive(populated_db: sqlite3.Connection) -> None:
    results = services.search_books(populated_db, "clean")
    assert len(results) == 1


def test_search_books_no_results(populated_db: sqlite3.Connection) -> None:
    assert services.search_books(populated_db, "Kubernetes") == []


# ---------------------------------------------------------------------------
# update_book / delete_book
# ---------------------------------------------------------------------------

def test_update_book_changes_title(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    from bookshelf.models import BookUpdate

    created = services.create_book(db_conn, sample_book)
    updated = services.update_book(db_conn, created.id, BookUpdate(title="New Title"))
    assert updated is not None
    assert updated.title == "New Title"
    assert updated.author == sample_book.author


def test_update_book_not_found_returns_none(db_conn: sqlite3.Connection) -> None:
    from bookshelf.models import BookUpdate

    result = services.update_book(db_conn, 999, BookUpdate(title="X"))
    assert result is None


def test_delete_book_returns_true_when_found(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    created = services.create_book(db_conn, sample_book)
    assert services.delete_book(db_conn, created.id) is True
    assert services.get_book(db_conn, created.id) is None


def test_delete_book_returns_false_when_not_found(db_conn: sqlite3.Connection) -> None:
    assert services.delete_book(db_conn, 999) is False


# ---------------------------------------------------------------------------
# reviews
# ---------------------------------------------------------------------------

def test_add_review_returns_response(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    created = services.create_book(db_conn, sample_book)
    review = ReviewCreate(rating=5, text="Essential reading.", reviewer="alice")
    result = services.add_review(db_conn, created.id, review)
    assert result is not None
    assert result.rating == 5
    assert result.book_id == created.id


def test_add_review_book_not_found_returns_none(db_conn: sqlite3.Connection) -> None:
    review = ReviewCreate(rating=5, text="Great.", reviewer="alice")
    assert services.add_review(db_conn, 999, review) is None


def test_list_reviews_returns_all_for_book(
    populated_db: sqlite3.Connection,
) -> None:
    reviews = services.list_reviews(populated_db, 1)
    assert reviews is not None
    assert len(reviews) == 2


def test_list_reviews_book_not_found_returns_none(db_conn: sqlite3.Connection) -> None:
    assert services.list_reviews(db_conn, 999) is None


# ---------------------------------------------------------------------------
# get_top_books
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_get_top_books_normal(populated_db: sqlite3.Connection) -> None:
    results = services.get_top_books(populated_db, 2)
    assert len(results) == 2


@pytest.mark.slow
def test_get_top_books_zero_n(populated_db: sqlite3.Connection) -> None:
    assert services.get_top_books(populated_db, 0) == []


@pytest.mark.slow
def test_get_top_books_n_exceeds_total(populated_db: sqlite3.Connection) -> None:
    all_books = services.list_books(populated_db)
    results = services.get_top_books(populated_db, 999)
    assert len(results) == len(all_books)


def test_get_top_books_no_reviews(
    db_conn: sqlite3.Connection, sample_book: BookCreate
) -> None:
    services.create_book(db_conn, sample_book)
    results = services.get_top_books(db_conn, 1)
    assert len(results) == 1
