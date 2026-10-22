from fastapi.testclient import TestClient


def test_add_review_returns_201(client: TestClient) -> None:
    book = client.post("/books/", json={
        "title": "Clean Code",
        "author": "Robert Martin",
        "isbn": "9780132350884",
        "year": 2008,
    }).json()

    response = client.post(f"/books/{book['id']}/reviews", json={
        "rating": 5,
        "text": "Essential reading.",
        "reviewer": "alice",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["reviewer"] == "alice"
    assert data["book_id"] == book["id"]


def test_add_review_to_nonexistent_book_returns_404(client: TestClient) -> None:
    response = client.post("/books/99999/reviews", json={
        "rating": 5,
        "text": "Great.",
        "reviewer": "alice",
    })
    assert response.status_code == 404


def test_list_reviews_for_book(client: TestClient) -> None:
    book = client.post("/books/", json={
        "title": "Design Patterns",
        "author": "Gang of Four",
        "isbn": "9780201633610",
        "year": 1994,
    }).json()

    client.post(f"/books/{book['id']}/reviews", json={"rating": 4, "text": "Classic.", "reviewer": "alice"})
    client.post(f"/books/{book['id']}/reviews", json={"rating": 5, "text": "Essential.", "reviewer": "bob"})

    response = client.get(f"/books/{book['id']}/reviews")
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 2
    reviewers = {r["reviewer"] for r in reviews}
    assert reviewers == {"alice", "bob"}


def test_list_reviews_for_nonexistent_book_returns_404(client: TestClient) -> None:
    response = client.get("/books/99999/reviews")
    assert response.status_code == 404


def test_review_rating_out_of_range_returns_422(client: TestClient) -> None:
    book = client.post("/books/", json={
        "title": "Clean Code",
        "author": "Robert Martin",
        "isbn": "9780132350884",
        "year": 2008,
    }).json()

    response = client.post(f"/books/{book['id']}/reviews", json={
        "rating": 6,
        "text": "Off the charts.",
        "reviewer": "alice",
    })
    assert response.status_code == 422
