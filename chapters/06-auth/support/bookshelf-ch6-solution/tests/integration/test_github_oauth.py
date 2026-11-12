"""GitHub login, with GitHub replaced by an httpx.MockTransport."""

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from bookshelf.auth import github

Handler = Callable[[httpx.Request], httpx.Response]


def fake_github(
    user_id: int = 583231, login: str = "octocat", token_error: str | None = None
) -> tuple[Handler, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url == github.TOKEN_URL:
            if token_error:
                return httpx.Response(
                    200,
                    json={"error": token_error, "error_description": "bad code"},
                )
            return httpx.Response(
                200, json={"access_token": "gho_fake", "token_type": "bearer"}
            )
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": user_id, "login": login})
        if request.url.path == "/user/emails":
            return httpx.Response(
                200,
                json=[
                    {"email": "old@example.com", "primary": False, "verified": True},
                    {"email": "octo@example.com", "primary": True, "verified": True},
                ],
            )
        return httpx.Response(404)

    return handler, calls


@pytest.fixture
def use_fake_github(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _install(handler: Handler) -> None:
        monkeypatch.setattr(
            github,
            "_client",
            lambda: httpx.Client(transport=httpx.MockTransport(handler)),
        )

    return _install


def start_login(client: TestClient) -> str:
    response = client.get("/auth/github", follow_redirects=False)
    assert response.status_code == 307
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["test-client-id"]
    assert query["scope"] == ["read:user user:email"]
    return query["state"][0]


def test_login_redirects_to_github_with_state(client: TestClient) -> None:
    response = client.get("/auth/github", follow_redirects=False)
    location = response.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize?")
    state = parse_qs(urlparse(location).query)["state"][0]
    assert client.cookies["oauth_state"] == state
    assert "HttpOnly" in response.headers["set-cookie"]


def test_callback_creates_user_and_returns_tokens(
    client: TestClient,
    use_fake_github,  # type: ignore[no-untyped-def]
) -> None:
    handler, calls = fake_github()
    use_fake_github(handler)
    state = start_login(client)

    response = client.get(f"/auth/github/callback?code=abc123&state={state}")

    assert response.status_code == 200, response.json()
    tokens = response.json()
    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json() == {"id": 1, "username": "github:octocat", "role": "user"}
    # The code exchange is a server-to-server POST carrying our client secret.
    token_request = calls[0]
    assert token_request.method == "POST"
    assert b"client_secret=test-client-secret" in token_request.content
    assert b"code=abc123" in token_request.content


def test_second_login_finds_same_user(
    client: TestClient,
    use_fake_github,  # type: ignore[no-untyped-def]
) -> None:
    handler, _ = fake_github()
    use_fake_github(handler)

    ids = []
    for _ in range(2):
        state = start_login(client)
        tokens = client.get(f"/auth/github/callback?code=c&state={state}").json()
        me = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        ids.append(me.json()["id"])
    assert ids == [1, 1]


def test_callback_rejects_wrong_state(
    client: TestClient,
    use_fake_github,  # type: ignore[no-untyped-def]
) -> None:
    handler, calls = fake_github()
    use_fake_github(handler)
    start_login(client)

    response = client.get("/auth/github/callback?code=c&state=forged")

    assert response.status_code == 400
    assert calls == []  # never talked to GitHub


def test_callback_rejects_missing_state_cookie(client: TestClient) -> None:
    response = client.get("/auth/github/callback?code=c&state=anything")
    assert response.status_code == 400


def test_callback_handles_github_error_in_200_body(
    client: TestClient,
    use_fake_github,  # type: ignore[no-untyped-def]
) -> None:
    handler, _ = fake_github(token_error="bad_verification_code")
    use_fake_github(handler)
    state = start_login(client)

    response = client.get(f"/auth/github/callback?code=reused&state={state}")

    assert response.status_code == 400
    assert response.json()["detail"] == "bad code"


def test_github_not_configured_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bookshelf.auth.config import get_settings

    monkeypatch.delenv("GITHUB_CLIENT_ID")
    get_settings.cache_clear()
    assert client.get("/auth/github", follow_redirects=False).status_code == 503
