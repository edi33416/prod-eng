from unittest.mock import MagicMock, patch

import httpx
import pytest

from bookshelf.isbn_service import validate_isbn_remote


def test_validate_isbn_remote_found() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"ISBN:9780135957059": {"title": "The Pragmatic Programmer"}}
    mock_response.raise_for_status.return_value = None

    with patch("bookshelf.isbn_service.httpx.get", return_value=mock_response):
        result = validate_isbn_remote("9780135957059")

    assert result is True


def test_validate_isbn_remote_not_found() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None

    with patch("bookshelf.isbn_service.httpx.get", return_value=mock_response):
        result = validate_isbn_remote("9780000000000")

    assert result is False


def test_validate_isbn_remote_timeout() -> None:
    with patch(
        "bookshelf.isbn_service.httpx.get",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        with pytest.raises(httpx.TimeoutException):
            validate_isbn_remote("9780135957059")


def test_validate_isbn_remote_http_error() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=MagicMock(),
    )

    with patch("bookshelf.isbn_service.httpx.get", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            validate_isbn_remote("9780135957059")


def test_validate_isbn_remote_calls_correct_url() -> None:
    mock_get = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with patch("bookshelf.isbn_service.httpx.get", mock_get):
        validate_isbn_remote("9780135957059")

    mock_get.assert_called_once_with(
        "https://openlibrary.org/api/books",
        params={"bibkeys": "ISBN:9780135957059", "format": "json"},
        timeout=5.0,
    )
