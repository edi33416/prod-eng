from fastapi.testclient import TestClient

ALLOWED = "https://bookshelf.example.com"


def test_preflight_from_allowed_origin(client: TestClient) -> None:
    response = client.options(
        "/books/",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]


def test_preflight_from_other_origin_rejected(client: TestClient) -> None:
    response = client.options(
        "/books/",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_other_origin_has_no_cors_header(
    client: TestClient,
) -> None:
    response = client.get("/books/", headers={"Origin": "https://evil.example"})
    # The server still answers; the *browser* refuses to hand the response
    # to the page's JavaScript.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
