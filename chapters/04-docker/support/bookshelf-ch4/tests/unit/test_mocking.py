import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from bookshelf import services
from bookshelf.models import BookResponse, ReviewCreate


def test_add_review_book_not_found_skips_insert() -> None:
    mock_conn = MagicMock(spec=sqlite3.Connection)
    review = ReviewCreate(rating=4, text="Good book.", reviewer="alice")

    with patch("bookshelf.services.get_book", return_value=None):
        result = services.add_review(mock_conn, 999, review)

    assert result is None
    mock_conn.execute.assert_not_called()


def test_add_review_propagates_db_error() -> None:
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_book = BookResponse(
        id=1, title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
    )
    review = ReviewCreate(rating=5, text="Essential.", reviewer="alice")

    with patch("bookshelf.services.get_book", return_value=mock_book):
        mock_conn.execute.side_effect = sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            services.add_review(mock_conn, 1, review)


def test_add_review_db_insert_fails() -> None:
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_book = BookResponse(
        id=1, title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
    )
    review = ReviewCreate(rating=5, text="Great.", reviewer="alice")

    with patch("bookshelf.services.get_book", return_value=mock_book):
        mock_conn.execute.side_effect = Exception("constraint violation")

        with pytest.raises(Exception, match="constraint violation"):
            services.add_review(mock_conn, 1, review)
