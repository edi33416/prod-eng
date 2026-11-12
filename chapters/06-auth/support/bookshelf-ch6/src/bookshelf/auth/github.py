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
    # TODO(ch6): POST the code to TOKEN_URL (Accept: application/json), check
    # the body for "error" (GitHub answers 200 even on failure), then GET
    # /user and /user/emails with the access token.
    raise NotImplementedError
