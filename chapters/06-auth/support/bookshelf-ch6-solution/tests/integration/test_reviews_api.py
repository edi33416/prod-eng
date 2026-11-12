from fastapi.testclient import TestClient

from tests.integration.conftest import TokenFactory


def test_add_review_returns_201(auth_client: TestClient, create_book) -> None:  # type: ignore[type-arg]
    book = create_book(title="Clean Code")

    response = auth_client.post(
        f"/books/{book['id']}/reviews",
        json={"rating": 5, "text": "Essential reading."},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["reviewer"] == "test-user"
    assert data["book_id"] == book["id"]


def test_reviewer_in_body_is_ignored(auth_client: TestClient, create_book) -> None:  # type: ignore[type-arg]
    book = create_book()

    response = auth_client.post(
        f"/books/{book['id']}/reviews",
        json={"rating": 1, "text": "Terrible.", "reviewer": "someone-else"},
    )
    assert response.status_code == 201
    assert response.json()["reviewer"] == "test-user"


def test_add_review_to_nonexistent_book_returns_404(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/books/99999/reviews", json={"rating": 5, "text": "Great."}
    )
    assert response.status_code == 404


def test_list_reviews_for_book(
    client: TestClient,
    create_book,  # type: ignore[no-untyped-def]
    make_token: TokenFactory,
) -> None:
    book = create_book(title="Design Patterns")
    for username, rating in [("alice", 4), ("bob", 5)]:
        token = make_token(username=username)
        response = client.post(
            f"/books/{book['id']}/reviews",
            json={"rating": rating, "text": "Classic."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    response = client.get(f"/books/{book['id']}/reviews")
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 2
    assert {r["reviewer"] for r in reviews} == {"alice", "bob"}


def test_list_reviews_for_nonexistent_book_returns_404(client: TestClient) -> None:
    response = client.get("/books/99999/reviews")
    assert response.status_code == 404


def test_review_rating_out_of_range_returns_422(
    auth_client: TestClient,
    create_book,  # type: ignore[no-untyped-def]
) -> None:
    book = create_book()

    response = auth_client.post(
        f"/books/{book['id']}/reviews",
        json={"rating": 6, "text": "Off the charts."},
    )
    assert response.status_code == 422
