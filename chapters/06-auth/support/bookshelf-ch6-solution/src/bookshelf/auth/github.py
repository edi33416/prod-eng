from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105
API_URL = "https://api.github.com"
SCOPES = "read:user user:email"


class GitHubOAuthError(Exception):
    pass


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    email: str | None


def _client() -> httpx.Client:
    # One place to build the HTTP client, so tests can swap in a fake transport.
    return httpx.Client(timeout=10.0)


def authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "allow_signup": "false",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str
) -> GitHubUser:
    with _client() as http:
        token_resp = http.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        # GitHub answers 200 OK even for a bad or reused code; the error is
        # in the body.
        if "error" in token_data:
            raise GitHubOAuthError(token_data.get("error_description", "OAuth error"))
        access_token = token_data["access_token"]

        api_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        user_resp = http.get(f"{API_URL}/user", headers=api_headers)
        user_resp.raise_for_status()
        user = user_resp.json()

        # /user only shows an email the user made public. /user/emails (scope
        # user:email) lists all of them, with a "verified" flag.
        emails_resp = http.get(f"{API_URL}/user/emails", headers=api_headers)
        emails_resp.raise_for_status()
        email = next(
            (
                e["email"]
                for e in emails_resp.json()
                if e.get("primary") and e.get("verified")
            ),
            None,
        )
    return GitHubUser(id=int(user["id"]), login=str(user["login"]), email=email)
