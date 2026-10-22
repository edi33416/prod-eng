# Integration tests for the Reviews API endpoints.
#
# TODO: Add the `client` fixture to tests/integration/conftest.py before
# implementing these tests. See the "Integration Testing with TestClient"
# section of Chapter 3 for the fixture implementation.

from fastapi.testclient import TestClient


def test_add_review_returns_201(client: TestClient) -> None:
    # TODO: Create a book first, then POST /books/{id}/reviews
    # Assert response.status_code == 201
    # Assert the response contains rating, text, reviewer, book_id
    pass


def test_add_review_to_nonexistent_book_returns_404(client: TestClient) -> None:
    # TODO: POST /books/99999/reviews
    # Assert response.status_code == 404
    pass


def test_list_reviews_for_book(client: TestClient) -> None:
    # TODO: Create a book, add 2 reviews, then GET /books/{id}/reviews
    # Assert response.status_code == 200
    # Assert len(reviews) == 2
    pass


def test_list_reviews_for_nonexistent_book_returns_404(client: TestClient) -> None:
    # TODO: GET /books/99999/reviews
    # Assert response.status_code == 404
    pass


def test_review_rating_out_of_range_returns_422(client: TestClient) -> None:
    # TODO: Create a book, then POST a review with rating=6
    # Assert response.status_code == 422
    pass
