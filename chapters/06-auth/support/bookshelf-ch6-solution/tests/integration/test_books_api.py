from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


def test_create_book_returns_201(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/books/",
        json={
            "title": "The Pragmatic Programmer",
            "author": "David Thomas",
            "isbn": "9780135957059",
            "year": 1999,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "The Pragmatic Programmer"
    assert data["author"] == "David Thomas"
    assert data["isbn"] == "9780135957059"
    assert "id" in data


def test_get_book_returns_200(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/books/",
        json={
            "title": "Clean Code",
            "author": "Robert Martin",
            "isbn": "9780132350884",
            "year": 2008,
        },
    )
    book_id = create_response.json()["id"]

    response = auth_client.get(f"/books/{book_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Clean Code"


def test_list_books_empty(client: TestClient) -> None:
    response = client.get("/books/")
    assert response.status_code == 200
    assert response.json() == []


def test_list_books_returns_created_books(auth_client: TestClient, create_book) -> None:  # type: ignore[type-arg]
    create_book(title="Book A", isbn="9780000000001")
    create_book(title="Book B", isbn="9780000000002")
    create_book(title="Book C", isbn="9780000000003")

    response = auth_client.get("/books/")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_update_book_changes_title(auth_client: TestClient, create_book) -> None:  # type: ignore[type-arg]
    book = create_book(title="Old Title")
    response = auth_client.put(f"/books/{book['id']}", json={"title": "New Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"
    assert response.json()["author"] == book["author"]


def test_delete_book_removes_it(admin_client: TestClient, create_book) -> None:  # type: ignore[type-arg]
    book = create_book()
    response = admin_client.delete(f"/books/{book['id']}")
    assert response.status_code == 204

    response = admin_client.get(f"/books/{book['id']}")
    assert response.status_code == 404


def test_search_books_by_title(auth_client: TestClient) -> None:
    auth_client.post(
        "/books/",
        json={
            "title": "Clean Code",
            "author": "Robert Martin",
            "isbn": "9780132350884",
            "year": 2008,
        },
    )
    auth_client.post(
        "/books/",
        json={
            "title": "The Pragmatic Programmer",
            "author": "David Thomas",
            "isbn": "9780135957059",
            "year": 1999,
        },
    )

    response = auth_client.get("/books/search", params={"q": "Pragmatic"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["title"] == "The Pragmatic Programmer"


def test_top_books_returns_correct_order(auth_client: TestClient) -> None:
    book1 = auth_client.post(
        "/books/",
        json={
            "title": "High Rated",
            "author": "Author A",
            "isbn": "9780000000001",
            "year": 2020,
        },
    ).json()
    book2 = auth_client.post(
        "/books/",
        json={
            "title": "Low Rated",
            "author": "Author B",
            "isbn": "9780000000002",
            "year": 2020,
        },
    ).json()

    auth_client.post(
        f"/books/{book1['id']}/reviews",
        json={"rating": 5, "text": "Great"},
    )
    auth_client.post(
        f"/books/{book1['id']}/reviews",
        json={"rating": 5, "text": "Excellent"},
    )
    auth_client.post(
        f"/books/{book2['id']}/reviews",
        json={"rating": 2, "text": "Meh"},
    )

    response = auth_client.get("/books/top", params={"n": 1})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "High Rated"


def test_list_books_pagination(auth_client: TestClient) -> None:
    for i in range(5):
        auth_client.post(
            "/books/",
            json={
                "title": f"Book {i}",
                "author": "Author",
                "isbn": f"978000000000{i}",
                "year": 2020,
            },
        )

    page_1 = auth_client.get("/books/", params={"offset": 0, "limit": 2}).json()
    page_2 = auth_client.get("/books/", params={"offset": 2, "limit": 2}).json()
    page_3 = auth_client.get("/books/", params={"offset": 4, "limit": 2}).json()

    assert len(page_1) == 2
    assert len(page_2) == 2
    assert len(page_3) == 1

    page_1_ids = {b["id"] for b in page_1}
    page_2_ids = {b["id"] for b in page_2}
    assert page_1_ids.isdisjoint(page_2_ids)


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


def test_get_nonexistent_book_returns_404(client: TestClient) -> None:
    response = client.get("/books/99999")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_create_duplicate_isbn_returns_409(auth_client: TestClient) -> None:
    book_data = {
        "title": "Clean Code",
        "author": "Robert Martin",
        "isbn": "9780132350884",
        "year": 2008,
    }
    auth_client.post("/books/", json=book_data)
    response = auth_client.post("/books/", json=book_data)
    assert response.status_code == 409
    assert "ISBN" in response.json()["detail"]


def test_create_book_invalid_isbn_returns_422(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/books/",
        json={
            "title": "X",
            "author": "Y",
            "isbn": "not-an-isbn",
            "year": 2020,
        },
    )
    assert response.status_code == 422


def test_update_nonexistent_book_returns_404(auth_client: TestClient) -> None:
    response = auth_client.put("/books/99999", json={"title": "New Title"})
    assert response.status_code == 404


def test_delete_nonexistent_book_returns_404(admin_client: TestClient) -> None:
    response = admin_client.delete("/books/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Full data flow test
# ---------------------------------------------------------------------------


def test_book_review_full_flow(auth_client: TestClient) -> None:
    book = auth_client.post(
        "/books/",
        json={
            "title": "The Pragmatic Programmer",
            "author": "David Thomas",
            "isbn": "9780135957059",
            "year": 1999,
        },
    ).json()
    book_id = book["id"]

    ratings = [5, 4, 3]
    for rating in ratings:
        response = auth_client.post(
            f"/books/{book_id}/reviews",
            json={
                "rating": rating,
                "text": f"Rating {rating} stars.",
            },
        )
        assert response.status_code == 201

    reviews_response = auth_client.get(f"/books/{book_id}/reviews")
    assert reviews_response.status_code == 200
    reviews = reviews_response.json()
    assert len(reviews) == 3

    stored_ratings = sorted(r["rating"] for r in reviews)
    assert stored_ratings == sorted(ratings)
