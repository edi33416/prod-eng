"""Who may call what. One test per (endpoint, kind of caller) that matters."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TokenFactory

BOOK = {"title": "T", "author": "A", "isbn": "9780132350884", "year": 2008}


# ---------------------------------------------------------------------------
# 401: no token, bad token, expired token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/books/"),
        ("PUT", "/books/1"),
        ("DELETE", "/books/1"),
        ("POST", "/books/1/reviews"),
        ("GET", "/auth/me"),
    ],
)
def test_protected_endpoints_require_token(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json=BOOK)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "path", ["/books/", "/books/1", "/books/search?q=x", "/books/top", "/health"]
)
def test_read_endpoints_are_public(client: TestClient, path: str) -> None:
    assert client.get(path).status_code in (200, 404)


def test_expired_token_returns_401(
    client: TestClient, make_token: TokenFactory
) -> None:
    token = make_token(expires_delta=timedelta(seconds=-1))
    response = client.post(
        "/books/", json=BOOK, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token expired"


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-jwt",
        "Bearer eyJhbGciOiJIUzI1NiJ9.e30.ZRrHA1JJJW8opsbCGfG_HACGpVUMN_a9IV7pAx_Zmeo",
        "Basic YWxpY2U6c2VjcmV0",
    ],
)
def test_invalid_token_returns_401(client: TestClient, header: str) -> None:
    response = client.post("/books/", json=BOOK, headers={"Authorization": header})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 403: authenticated, but not allowed
# ---------------------------------------------------------------------------


def test_user_cannot_delete_book(
    client: TestClient,
    create_book,  # type: ignore[no-untyped-def]
    auth_headers: dict[str, str],
) -> None:
    book = create_book()
    response = client.delete(f"/books/{book['id']}", headers=auth_headers)
    assert response.status_code == 403
    assert client.get(f"/books/{book['id']}").status_code == 200


def test_admin_can_delete_book(
    client: TestClient,
    create_book,  # type: ignore[no-untyped-def]
    admin_headers: dict[str, str],
) -> None:
    book = create_book()
    response = client.delete(f"/books/{book['id']}", headers=admin_headers)
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# 2xx: valid access
# ---------------------------------------------------------------------------


def test_user_can_create_book(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/books/", json=BOOK, headers=auth_headers)
    assert response.status_code == 201


def test_user_can_review(
    client: TestClient,
    create_book,  # type: ignore[no-untyped-def]
    auth_headers: dict[str, str],
) -> None:
    book = create_book()
    response = client.post(
        f"/books/{book['id']}/reviews",
        json={"rating": 4, "text": "Good."},
        headers=auth_headers,
    )
    assert response.status_code == 201
