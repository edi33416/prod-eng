.. _ch06_oauth2:

OAuth 2.0 and Social Login
===========================

Logging In as Someone Else's Email Address
-------------------------------------------

In June 2023, the security firm Descope disclosed an attack it called **nOAuth**. Many
applications offered "Log in with Microsoft" and, after the OAuth flow, identified the
user by the ``email`` claim that Microsoft's identity platform sent back. In Azure AD
(now Entra ID), the email attribute of an account was **editable by the account's
administrator** and not verified. An attacker could create their own Azure tenant, set
their account's email to ``ceo@victim.com``, log in to the application with Microsoft,
and be handed the CEO's account.

Microsoft's login worked correctly and so did OAuth. The applications made the mistake:
they used a **mutable, unverified** attribute as the identity key, when the provider also
sent a stable, unique ID.

Keep that in mind on this page. OAuth 2.0 is a protocol for getting **delegated
access**. What your application does with the result, and especially how it maps an
external account to a local user, is your responsibility.

-----

What OAuth 2.0 Is For
----------------------

The problem OAuth solves: the BookShelf API wants to know who a user is on GitHub
without asking for their GitHub password. Before OAuth, applications asked for the
password ("enter your Gmail password so we can find your friends") and kept it. OAuth
replaces the password with a **limited, revocable token** that GitHub issues to the
application after the user approves.

Four roles:

**Resource owner**
   The user. Owns the GitHub account.

**Client**
   The BookShelf API. Wants limited access to the user's GitHub data.

**Authorization server**
   ``github.com/login/oauth/…``. Authenticates the user, asks for consent, issues tokens.

**Resource server**
   ``api.github.com``. Accepts the token and returns data. (Often operated by the same
   company as the authorization server, as here.)

and three terms:

**Scopes**
   What the client asks to do. We ask for ``read:user user:email``: read the profile and
   the email addresses, nothing else. The consent screen lists them.

**Authorization code**
   A short-lived, single-use code that GitHub hands back **through the browser**. It is
   useless without the client secret.

**State**
   A random value the client generates, sends through the browser, and checks on the way
   back. This is CSRF protection for the login flow, explained below.

-----

The Authorization Code Flow
----------------------------

Read this sequence until you can draw it from memory. The code comes after it.

.. code-block:: text

   Browser                     BookShelf API                 GitHub
     │ 1. GET /auth/github          │                            │
     │─────────────────────────────▶│ generate state             │
     │ 2. 307 → github.com/login/   │                            │
     │    oauth/authorize?client_id │                            │
     │    &scope&state + state cookie                            │
     │◀─────────────────────────────│                            │
     │ 3. GET authorize?...                                      │
     │──────────────────────────────────────────────────────────▶│ user logs in to
     │                                                           │ GitHub, approves
     │ 4. 302 → localhost:8000/auth/github/callback?code&state   │ the scopes
     │◀──────────────────────────────────────────────────────────│
     │ 5. GET /auth/github/callback?code&state (+ state cookie)  │
     │─────────────────────────────▶│ state == cookie?           │
     │                              │ 6. POST access_token       │
     │                              │    code + client_secret    │
     │                              │───────────────────────────▶│ (server-to-server)
     │                              │    {access_token: gho_...} │
     │                              │◀───────────────────────────│
     │                              │ 7. GET api.github.com/user │
     │                              │───────────────────────────▶│
     │                              │    {id: 583231, login: ...}│
     │                              │◀───────────────────────────│
     │                              │ 8. find/create local user  │
     │ 9. {access_token: <BookShelf JWT>, refresh_token}         │
     │◀─────────────────────────────│                            │

Three things to notice:

- The user types their password **only into github.com** (step 3). The BookShelf API
  never sees it.
- The browser carries the **code** (steps 4–5), but the code is worthless without the
  **client secret**, which only travels server-to-server (step 6). The GitHub access
  token never reaches the browser.
- At the end (step 9), the user holds a **BookShelf** JWT, the same kind that
  ``/auth/login`` issues. From this point on GitHub is out of the picture. Every
  protected endpoint works exactly as before.

**Why the state parameter?** Without it, an attacker can start a GitHub login with
**their own** GitHub account, stop at step 4, and trick the victim's browser into
loading the callback URL with the attacker's code (a link, a hidden image). The victim
is now logged in to BookShelf **as the attacker**, and anything they do (write reviews,
enter data) lands in the attacker's account. With state, the callback only accepts a
value that **this browser** received in step 2, stored in a cookie that other sites can
neither read nor set.

.. admonition:: Crash Course: OAuth 2.0 Grant Types
   :class: dropdown

   A **grant type** is a way for a client to obtain an access token. OAuth 2.0 (RFC 6749)
   defined four. Best practice since then (RFC 9700, and the OAuth 2.1 draft) has
   removed two.

   .. list-table::
      :header-rows: 1
      :widths: 24 38 38

      * - Grant
        - How
        - Use it?
      * - Authorization Code
        - Browser redirect, code exchanged server-side with the client secret
        - **Yes**, for web apps with a backend (this page)
      * - Authorization Code + PKCE
        - Like above. The client also sends ``code_challenge = SHA256(verifier)``
          first, and the ``verifier`` with the exchange
        - **Yes**, for SPAs and mobile apps, which cannot keep a secret. OAuth 2.1 makes
          PKCE mandatory for **all** clients
      * - Client Credentials
        - ``POST /token`` with client ID + secret; no user involved
        - **Yes**, for service-to-service calls
      * - Device Code
        - The device shows a code; the user approves on another device
        - **Yes**, for TVs, CLIs (``gh auth login`` uses it)
      * - Implicit
        - Access token returned directly in the redirect URL fragment
        - **No.** Deprecated: tokens leak through browser history and referrers
      * - Resource Owner Password
        - The client collects the user's password and sends it to the token endpoint
        - **No.** Defeats the purpose of OAuth

   PKCE ("pixy", RFC 7636) protects against a stolen **code**: an attacker who
   intercepts the redirect does not know the verifier, so cannot exchange the code. The
   Keycloak lab in :ref:`ch06_sso` uses it. GitHub supports PKCE for OAuth Apps, and
   adding it to the BookShelf flow is exercise 3.

   For a deeper dive: `RFC 9700 — OAuth 2.0 Security Best Current Practice
   <https://www.rfc-editor.org/rfc/rfc9700>`_

-----

Registering a GitHub OAuth App
-------------------------------

On GitHub: **Settings → Developer settings → OAuth Apps → New OAuth App**.

.. list-table::
   :widths: 35 65

   * - Application name
     - ``BookShelf (dev, <your-username>)``
   * - Homepage URL
     - ``http://localhost:8000``
   * - Authorization callback URL
     - ``http://localhost:8000/auth/github/callback``

After **Register application**, copy the **Client ID** and click **Generate a new client
secret**. GitHub shows the secret **once**. Put both in ``.env``:

.. code-block:: bash

   GITHUB_CLIENT_ID=Ov23li...
   GITHUB_CLIENT_SECRET=...
   COOKIE_SECURE=false        # plain-HTTP localhost only; see below

The callback URL must match exactly, including the port. GitHub refuses to redirect
anywhere else, which is what stops an attacker from receiving codes meant for you. Use a
separate OAuth App per environment (dev, staging, production), each with its own
callback URL and secret.

-----

Implementation
---------------

Talking to GitHub (``auth/github.py``):

.. code-block:: python

   AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
   TOKEN_URL = "https://github.com/login/oauth/access_token"
   API_URL = "https://api.github.com"
   SCOPES = "read:user user:email"


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
           ...  # GET /user and /user/emails with the access token

Two GitHub-specific traps are handled here:

- The token endpoint returns **200 OK** with ``{"error": "bad_verification_code"}`` when
  the code is wrong, expired or already used. ``raise_for_status()`` passes, and code
  that only checks the status crashes with ``KeyError: 'access_token'``.
- ``GET /user`` returns ``"email": null`` unless the user made an address public. The
  ``user:email`` scope allows ``GET /user/emails``, which lists every address with
  ``primary`` and ``verified`` flags. We keep only the primary, verified one.

The endpoints (``routers/auth.py``):

.. code-block:: python

   @router.get("/github")
   def github_login() -> RedirectResponse:
       settings = get_settings()
       if not settings.github_client_id:
           raise HTTPException(status_code=503, detail="GitHub login is not configured")
       state = secrets.token_urlsafe(32)
       response = RedirectResponse(
           github.authorization_url(
               settings.github_client_id, settings.github_redirect_uri, state
           )
       )
       # The browser keeps the state in a cookie only our site can read; the
       # callback checks that GitHub sent the same value back.
       response.set_cookie(
           _STATE_COOKIE,
           state,
           max_age=600,
           path="/auth/github",
           httponly=True,
           secure=settings.cookie_secure,
           samesite="lax",
       )
       return response


   @router.get("/github/callback", response_model=TokenResponse)
   def github_callback(
       code: str,
       state: str,
       response: Response,
       oauth_state: Annotated[str | None, Cookie()] = None,
   ) -> TokenResponse:
       settings = get_settings()
       ...
       if oauth_state is None or not secrets.compare_digest(state, oauth_state):
           raise HTTPException(status_code=400, detail="Invalid OAuth state")
       response.delete_cookie(_STATE_COOKIE, path="/auth/github")

       try:
           gh_user = github.exchange_code(code, ...)
       except github.GitHubOAuthError as exc:
           raise HTTPException(status_code=400, detail=str(exc)) from None

       with get_connection() as conn:
           user = auth_service.get_or_create_github_user(
               conn, gh_user.id, gh_user.login, gh_user.email
           )
           return _issue_tokens(conn, user)

``SameSite=Lax`` is required here, not ``Strict``. Step 5 is a top-level navigation
**from github.com**, and a ``Strict`` cookie would not be sent on it.
``secrets.compare_digest`` compares in constant time.

**Mapping the GitHub account to a local user** is where nOAuth went wrong:

.. code-block:: python

   def get_or_create_github_user(
       conn: Connection, github_id: int, login: str, email: str | None
   ) -> UserRecord:
       user = get_user_by_github_id(conn, github_id)
       if user is not None:
           return user
       # The "github:" prefix cannot collide with a registered username, because
       # registration only allows [a-z0-9_-].
       return create_user(
           conn, f"github:{login.lower()}", None, github_id=github_id, email=email
       )

The key is GitHub's numeric ``id``, which never changes. The ``login`` can be renamed,
and after a rename someone else can claim the old name. The email is stored for
information only and never used to find an account. The local username gets a
``github:`` prefix that registration's username pattern does not allow, so nobody can
register ``github:octocat`` with a password and wait for the real octocat. GitHub
accounts have ``password_hash = NULL``. ``verify_password`` treats that as "no password
can match" and still spends the time on the dummy hash.

-----

Trying It
----------

Without credentials configured, the endpoint says so instead of redirecting to a broken
URL:

.. code-block:: bash

   $ curl -si localhost:8000/auth/github | sed -n '1p;$p'
   HTTP/1.1 503 Service Unavailable
   {"detail":"GitHub login is not configured"}

With ``GITHUB_CLIENT_ID`` set:

.. code-block:: bash

   $ curl -si localhost:8000/auth/github
   HTTP/1.1 307 Temporary Redirect
   date: Thu, 12 Nov 2026 12:12:15 GMT
   server: uvicorn
   content-length: 0
   location: https://github.com/login/oauth/authorize?client_id=Ov23liT6xKqZ0aBcD1eF&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fgithub%2Fcallback&scope=read%3Auser+user%3Aemail&state=WlozpKb-WeSzWP8u0vCQtownj5tEkfN5lmHgy4yRbz0&allow_signup=false
   set-cookie: oauth_state=WlozpKb-WeSzWP8u0vCQtownj5tEkfN5lmHgy4yRbz0; HttpOnly; Max-Age=600; Path=/auth/github; SameSite=lax
   vary: Origin

The same random value is in the ``location`` and in the cookie. A forged callback is
rejected before any request reaches GitHub:

.. code-block:: bash

   $ curl -si "localhost:8000/auth/github/callback?code=abc&state=forged" | sed -n '1p;$p'
   HTTP/1.1 400 Bad Request
   {"detail":"Invalid OAuth state"}

Now open http://localhost:8000/auth/github **in a browser**. GitHub asks you to log in
(if you are not already) and to authorize the app, listing the two scopes. After
**Authorize**, the browser lands on the callback and shows the JSON token response. The
exact output depends on your account:

.. code-block:: json

   {"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzIiwidXNlcm5hbWUiOiJnaXRodWI6...","refresh_token":"...","token_type":"bearer","expires_in":900}

.. code-block:: bash

   $ curl -s localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
   {"id":3,"username":"github:<your-login>","role":"user"}

Log in through GitHub a second time and you get the same ``id``. Revoke the app on
GitHub (**Settings → Applications → Authorized OAuth Apps**) and the next GitHub login
asks for consent again.

.. note::

   Returning tokens as a JSON page is a lab shortcut, because there is no frontend. A
   real web application ends the callback with a redirect to its own UI, delivering the
   refresh token as an ``HttpOnly`` cookie (:ref:`ch06_refresh_tokens`, exercise 3).
   **Never** put tokens in the redirect URL's query string, where they end up in browser
   history, server logs and ``Referer`` headers.

-----

**Exercises**

#. Create your GitHub OAuth App, implement ``exchange_code``, ``github_login`` and
   ``github_callback``, and complete the browser flow. Then use the returned JWT with
   ``curl`` to create a book and post a review. Check in the database that the
   ``users`` row has a ``github_id`` and a ``NULL`` ``password_hash``.

#. Call the callback twice with the same code (copy the URL from the browser's address
   bar after the first successful login, and reload it). What does GitHub answer, and
   what does the BookShelf API return? Which line of ``exchange_code`` handles it?

#. Add PKCE: in ``github_login``, generate a ``code_verifier``
   (``secrets.token_urlsafe(48)``), send ``code_challenge`` (base64url of its SHA-256,
   no padding) and ``code_challenge_method=S256`` in the authorization URL, keep the
   verifier in a second ``HttpOnly`` cookie, and send it as ``code_verifier`` in the
   token exchange. The function ``pkce_pair`` in ``support/keycloak/sso_demo.py`` shows
   the computation.

#. Add Google as a second provider using the same pattern (`Google's OAuth 2.0 for web
   servers <https://developers.google.com/identity/protocols/oauth2/web-server>`_).
   Store Google's stable ID (``sub``) in a new column. Then link accounts: if a Google
   login's email matches the email of an existing GitHub account, attach Google to that
   user instead of creating a new one. Write down exactly which conditions make that
   safe. Both providers must report the email as **verified**. What else? Re-read the
   nOAuth story before you answer.
