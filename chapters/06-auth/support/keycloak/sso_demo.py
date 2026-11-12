"""Walk through OIDC login and SSO against the local Keycloak, step by step.

A real user does this in a browser. This script plays the browser (it keeps
cookies and submits the login form) so that every request is visible.

    pip install httpx pyjwt[crypto]
    python sso_demo.py
"""

import base64
import hashlib
import html
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt

ISSUER = "http://localhost:8080/realms/bookshelf"
APPS = {
    "bookshelf-api": (
        "bookshelf-api-dev-secret",
        "http://localhost:8000/auth/oidc/callback",
    ),
    "bookshelf-admin-ui": (
        "bookshelf-admin-ui-dev-secret",
        "http://localhost:9000/callback",
    ),
}
USERNAME, PASSWORD = "alice", "alice-password-123"


class Browser:
    """Just enough of a browser: remembers cookies, does not follow redirects.

    Keycloak marks its cookies Secure. Browsers send Secure cookies to
    http://localhost (a "potentially trustworthy" origin); Python's cookie
    jar does not, so we keep the cookies ourselves.
    """

    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}
        self.http = httpx.Client(follow_redirects=False)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        header = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        resp = self.http.request(method, url, headers={"Cookie": header}, **kwargs)
        for raw in resp.headers.get_list("set-cookie"):
            name, _, rest = raw.partition("=")
            self.cookies[name] = rest.split(";", 1)[0]
        return resp


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def login(browser: Browser, config: dict, client_id: str) -> dict:
    secret, redirect_uri = APPS[client_id]
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    verifier, challenge = pkce_pair()

    print(f"\n=== {client_id} ===")
    # 1. The app redirects the browser to the IdP.
    url = config["authorization_endpoint"] + "?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    resp = browser.request("GET", url)

    if resp.status_code == 200:
        # 2. No IdP session yet: Keycloak shows its login form.
        print("[browser] IdP shows a login form -> submitting credentials")
        action = html.unescape(re.search(r'action="([^"]+)"', resp.text).group(1))
        resp = browser.request(
            "POST", action, data={"username": USERNAME, "password": PASSWORD}
        )
    else:
        print("[browser] IdP already has a session -> no login form")

    # 3. The IdP redirects back to the app with a one-time code.
    location = resp.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["state"] == [state], "state mismatch: possible CSRF"
    code = query["code"][0]
    print(f"[browser] redirected to {redirect_uri}?code={code[:12]}...")

    # 4. The app's backend exchanges the code (server-to-server).
    tokens = httpx.post(
        config["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        auth=(client_id, secret),
    ).json()
    print(f"[backend] token response keys: {sorted(tokens)}")

    # 5. Verify the ID token: signature (IdP's public key), iss, aud, exp, nonce.
    signing_key = jwt.PyJWKClient(config["jwks_uri"]).get_signing_key_from_jwt(
        tokens["id_token"]
    )
    claims = jwt.decode(
        tokens["id_token"],
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=ISSUER,
    )
    assert claims["nonce"] == nonce, "nonce mismatch: replayed ID token"
    print(f"[backend] ID token verified with key id {signing_key.key_id}")
    return claims


def main() -> None:
    config = httpx.get(f"{ISSUER}/.well-known/openid-configuration").json()
    browser = Browser()  # one browser, one cookie jar, two apps
    for client_id in APPS:
        claims = login(browser, config, client_id)
        shown = {k: claims[k] for k in ("iss", "aud", "sub", "email", "sid")}
        for key, value in shown.items():
            print(f"          {key:6} = {value}")


if __name__ == "__main__":
    main()
