import pytest
from fastapi.testclient import TestClient

from bookshelf.auth import service
from bookshelf.database import get_connection

PASSWORD = "correct horse battery staple"  # noqa: S105


def register(client: TestClient, username: str = "alice") -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/auth/register", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 201, response.json()
    return response.json()  # type: ignore[no-any-return]


def login(client: TestClient, username: str = "alice") -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_returns_user_without_password(client: TestClient) -> None:
    data = register(client)
    assert data == {"id": 1, "username": "alice", "role": "user"}


def test_register_cannot_choose_role(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"username": "mallory", "password": PASSWORD, "role": "admin"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_register_duplicate_returns_409(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/auth/register", json={"username": "alice", "password": PASSWORD}
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "username, password",
    [
        ("alice", "short"),  # password too short
        ("Alice", PASSWORD),  # uppercase not allowed
        ("github:alice", PASSWORD),  # reserved for GitHub accounts
        ("al", PASSWORD),  # username too short
        ("alice", "x" * 129),  # password too long
    ],
)
def test_register_validation(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_returns_token_pair(client: TestClient) -> None:
    register(client)
    tokens = login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["access_token"].count(".") == 2
    assert tokens["refresh_token"]


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/auth/login", json={"username": "alice", "password": "wrong password!"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_unknown_user_same_error(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"username": "nobody", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_rate_limited(client: TestClient) -> None:
    codes = [
        client.post(
            "/auth/login", json={"username": "alice", "password": "guess"}
        ).status_code
        for _ in range(7)
    ]
    assert codes == [401] * 5 + [429] * 2


def test_rate_limit_response_has_retry_after(client: TestClient) -> None:
    for _ in range(5):
        client.post("/auth/login", json={"username": "a", "password": "b"})
    response = client.post("/auth/login", json={"username": "a", "password": "b"})
    assert response.status_code == 429
    assert 0 < int(response.headers["retry-after"]) <= 60


def test_full_flow_register_login_use_token(client: TestClient) -> None:
    register(client)
    tokens = login(client)

    me = client.get("/auth/me", headers=bearer(tokens["access_token"]))
    assert me.json() == {"id": 1, "username": "alice", "role": "user"}

    response = client.post(
        "/books/",
        json={"title": "T", "author": "A", "isbn": "9780132350884", "year": 2008},
        headers=bearer(tokens["access_token"]),
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Refresh and logout
# ---------------------------------------------------------------------------


def test_refresh_returns_new_pair(client: TestClient) -> None:
    register(client)
    tokens = login(client)

    response = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    new = response.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    assert (
        client.get("/auth/me", headers=bearer(new["access_token"])).status_code == 200
    )


def test_refresh_token_single_use(client: TestClient) -> None:
    register(client)
    tokens = login(client)
    body = {"refresh_token": tokens["refresh_token"]}

    assert client.post("/auth/refresh", json=body).status_code == 200
    assert client.post("/auth/refresh", json=body).status_code == 401


def test_refresh_picks_up_role_change(client: TestClient) -> None:
    register(client)
    tokens = login(client)
    with get_connection() as conn:
        service.set_role(conn, "alice", "admin")

    # The old access token still says "user" until it expires...
    me = client.get("/auth/me", headers=bearer(tokens["access_token"]))
    assert me.json()["role"] == "user"
    # ...the next refresh reads the role from the database.
    new = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()
    me = client.get("/auth/me", headers=bearer(new["access_token"]))
    assert me.json()["role"] == "admin"


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    register(client)
    tokens = login(client)
    body = {"refresh_token": tokens["refresh_token"]}

    assert client.post("/auth/logout", json=body).status_code == 204
    assert client.post("/auth/refresh", json=body).status_code == 401


def test_logout_is_idempotent(client: TestClient) -> None:
    response = client.post("/auth/logout", json={"refresh_token": "unknown"})
    assert response.status_code == 204


def test_validation_error_does_not_echo_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register", json={"username": "bob", "password": "hunter2"}
    )
    assert response.status_code == 422
    assert "hunter2" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
