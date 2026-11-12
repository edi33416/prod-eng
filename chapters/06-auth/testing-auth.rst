.. _ch06_testing_auth:

Testing Authenticated Endpoints
================================

The Test That Was Never Written
--------------------------------

A refactor moves the book endpoints into a new router module. The reviewer checks that
the handlers are unchanged, CI is green, and the change ships. A week later someone
notices that ``DELETE /books/{id}`` no longer needs a token: the
``dependencies=[Depends(require_role("admin"))]`` argument stayed behind in the old file.
Every test still passed, because every test used an admin token, and **no test checked
that a request without one fails**.

Authorization bugs are invisible to tests that only cover the happy path. A test suite
for an authenticated API needs as many "this must be refused" tests as "this must work"
tests. It also has to stay fast, because once every write endpoint needs a token, a
naive suite logs in hundreds of times.

-----

Configuration for Every Test
-----------------------------

The settings are cached (``@lru_cache``) and the rate limiter keeps counts in memory. Both
would leak state between tests. An autouse fixture in the **root** ``tests/conftest.py``
gives every test the same known configuration:

.. code-block:: python

   TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-chars"  # noqa: S105


   @pytest.fixture(autouse=True)
   def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
       """Known auth configuration for every test, and a clean rate limiter."""
       monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
       # The test client talks plain HTTP; Secure cookies would never be sent.
       monkeypatch.setenv("COOKIE_SECURE", "false")
       monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
       monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
       get_settings.cache_clear()
       login_rate_limit.reset()
       yield
       get_settings.cache_clear()

This is why CI needs no ``JWT_SECRET_KEY`` secret. The test secret is in the repository
on purpose: it protects nothing. A ``ruff`` rule (S105, "hardcoded password") flags it,
and the ``noqa`` comment records that the decision was deliberate.

-----

Strategy 1: Mint Tokens Directly
---------------------------------

The login flow is tested once, in ``test_auth_api.py``. Every other test skips
registration and password hashing and creates a token with the application's own
``create_access_token`` (``tests/integration/conftest.py``):

.. code-block:: python

   @pytest.fixture
   def make_token() -> TokenFactory:
       def _make(
           user_id: int = 1,
           username: str = "test-user",
           role: str = "user",
           expires_delta: timedelta | None = None,
       ) -> str:
           return create_access_token(
               CurrentUser(id=user_id, username=username, role=role), expires_delta
           )

       return _make


   @pytest.fixture
   def auth_headers(make_token: TokenFactory) -> dict[str, str]:
       return {"Authorization": f"Bearer {make_token()}"}


   @pytest.fixture
   def admin_headers(make_token: TokenFactory) -> dict[str, str]:
       token = make_token(user_id=2, username="test-admin", role="admin")
       return {"Authorization": f"Bearer {token}"}

These are **real** tokens: signed, carrying ``exp``/``iss``/``aud``, and verified by the
real ``get_current_user``. A bug in token verification fails these tests. Only the
password check is skipped, and that is covered elsewhere.

``make_token`` is a factory fixture (:ref:`ch02_fixtures`), so one test can act as
several users:

.. code-block:: python

   def test_list_reviews_for_book(
       client: TestClient, create_book, make_token: TokenFactory
   ) -> None:
       book = create_book(title="Design Patterns")
       for username, rating in [("alice", 4), ("bob", 5)]:
           token = make_token(username=username)
           response = client.post(
               f"/books/{book['id']}/reviews",
               json={"rating": rating, "text": "Classic."},
               headers={"Authorization": f"Bearer {token}"},
           )
           assert response.status_code == 201

       response = client.get(f"/books/{book['id']}/reviews")
       assert {r["reviewer"] for r in response.json()} == {"alice", "bob"}

For the Chapter 5 tests, which are about books and not about auth, passing ``headers=``
to every call is noise. Two more fixtures wrap the client:

.. code-block:: python

   @pytest.fixture
   def auth_client(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
       """The same client, sending a "user" token with every request."""
       client.headers.update(auth_headers)
       return client

and ``admin_client`` likewise. Fixing the 13 failures from :ref:`ch06_implementing_jwt`
is then mostly a rename: tests that write use ``auth_client``, tests that delete use
``admin_client``, and read-only tests keep the anonymous ``client``.

.. warning::

   ``auth_client`` and ``admin_client`` modify the **same** ``client`` object. Do not
   request both in one test: the second silently overwrites the first's header. For
   tests that switch identity, use ``client`` with explicit ``headers=``.

-----

The Authorization Matrix
-------------------------

``test_authz.py`` is the test the opening story was missing. Parametrization
(:ref:`ch02_parametrize`) turns "every protected endpoint refuses anonymous callers"
into one test function:

.. code-block:: python

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


   def test_expired_token_returns_401(
       client: TestClient, make_token: TokenFactory
   ) -> None:
       token = make_token(expires_delta=timedelta(seconds=-1))
       response = client.post(
           "/books/", json=BOOK, headers={"Authorization": f"Bearer {token}"}
       )
       assert response.status_code == 401
       assert response.json()["detail"] == "Token expired"


   def test_user_cannot_delete_book(
       client: TestClient, create_book, auth_headers: dict[str, str]
   ) -> None:
       book = create_book()
       response = client.delete(f"/books/{book['id']}", headers=auth_headers)
       assert response.status_code == 403
       assert client.get(f"/books/{book['id']}").status_code == 200

An expired token needs no ``sleep()``: a **negative** ``expires_delta`` produces a token
that expired a second ago. ``test_user_cannot_delete_book`` checks the 403 **and** that
the book still exists. A handler that deletes first and checks permissions afterwards
would pass the first assertion alone.

The matrix also covers public endpoints. They must **stay** public: a catalog that
suddenly requires login breaks every anonymous client.

.. code-block:: text

   $ pytest tests/integration/test_authz.py tests/integration/test_github_oauth.py -v
   ...
   tests/integration/test_authz.py::test_protected_endpoints_require_token[POST-/books/] PASSED [  4%]
   tests/integration/test_authz.py::test_protected_endpoints_require_token[PUT-/books/1] PASSED [  8%]
   tests/integration/test_authz.py::test_protected_endpoints_require_token[DELETE-/books/1] PASSED [ 12%]
   tests/integration/test_authz.py::test_protected_endpoints_require_token[POST-/books/1/reviews] PASSED [ 16%]
   tests/integration/test_authz.py::test_protected_endpoints_require_token[GET-/auth/me] PASSED [ 20%]
   tests/integration/test_authz.py::test_read_endpoints_are_public[/books/] PASSED [ 24%]
   tests/integration/test_authz.py::test_read_endpoints_are_public[/books/1] PASSED [ 28%]
   tests/integration/test_authz.py::test_read_endpoints_are_public[/books/search?q=x] PASSED [ 32%]
   tests/integration/test_authz.py::test_read_endpoints_are_public[/books/top] PASSED [ 36%]
   tests/integration/test_authz.py::test_read_endpoints_are_public[/health] PASSED [ 40%]
   tests/integration/test_authz.py::test_expired_token_returns_401 PASSED   [ 44%]
   tests/integration/test_authz.py::test_invalid_token_returns_401[Bearer not-a-jwt] PASSED [ 48%]
   tests/integration/test_authz.py::test_invalid_token_returns_401[Bearer eyJhbGciOiJIUzI1NiJ9.e30.ZRrHA1JJJW8opsbCGfG_HACGpVUMN_a9IV7pAx_Zmeo] PASSED [ 52%]
   tests/integration/test_authz.py::test_invalid_token_returns_401[Basic YWxpY2U6c2VjcmV0] PASSED [ 56%]
   tests/integration/test_authz.py::test_user_cannot_delete_book PASSED     [ 60%]
   tests/integration/test_authz.py::test_admin_can_delete_book PASSED       [ 64%]
   tests/integration/test_authz.py::test_user_can_create_book PASSED        [ 68%]
   tests/integration/test_authz.py::test_user_can_review PASSED             [ 72%]

Now repeat the opening refactor: delete ``dependencies=[Depends(require_role("admin"))]``
from the ``DELETE`` route and run the suite. ``test_user_cannot_delete_book`` fails. The
bug that shipped in the story would not get past CI here.

-----

Strategy 2: Override the Dependency
------------------------------------

FastAPI can replace any dependency for the duration of a test:

.. code-block:: python

   @pytest.fixture
   def as_admin() -> Iterator[None]:
       app.dependency_overrides[get_current_user] = lambda: CurrentUser(
           id=2, username="test-admin", role="admin"
       )
       yield
       app.dependency_overrides.clear()

Every request in the test is now treated as coming from an admin, with no token at all.
It is the fastest option and needs no secret. The cost: **none of the token code runs**.
Signature checks, expiry, the ``WWW-Authenticate`` header and ``require_role``'s use of
``get_current_user`` are all bypassed.

.. list-table::
   :header-rows: 1
   :widths: 26 37 37

   * -
     - Minted tokens (strategy 1)
     - Dependency override (strategy 2)
   * - Exercises token verification
     - Yes
     - No
   * - Can test 401 / expired / forged
     - Yes
     - No
   * - Needs a test secret
     - Yes
     - No
   * - Use for
     - Everything by default
     - Tests where auth is irrelevant and token setup is costly, e.g. testing an
       endpoint's business logic in isolation

The BookShelf suite uses strategy 1 throughout. ``support/test-auth-fixtures.py``
contains both, ready to copy.

-----

Mocking the OAuth Provider
---------------------------

Tests must never call the real GitHub: it needs a browser, a real account, network
access, and it would make CI depend on GitHub's uptime. Chapter 3 mocked
``httpx.get`` with ``unittest.mock.patch``. For a multi-step exchange (POST token, GET
user, GET emails), httpx offers something more convenient, ``MockTransport``: a
function that receives each ``httpx.Request`` and returns an ``httpx.Response``, as if
it were the server.

``github.py`` builds its client in one function, ``_client()``, precisely so a test can
swap it:

.. code-block:: python

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
               return httpx.Response(200, json=[...])
           return httpx.Response(404)

       return handler, calls


   @pytest.fixture
   def use_fake_github(monkeypatch: pytest.MonkeyPatch):
       def _install(handler: Handler) -> None:
           monkeypatch.setattr(
               github,
               "_client",
               lambda: httpx.Client(transport=httpx.MockTransport(handler)),
           )

       return _install

A test drives the whole flow through the real endpoints: start the login, take the
``state`` from the redirect, call the callback with it:

.. code-block:: python

   def test_callback_creates_user_and_returns_tokens(
       client: TestClient, use_fake_github
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

The recorded ``calls`` let the test assert on what we **sent**, not just on what we
did with the answer. ``test_callback_rejects_wrong_state`` asserts ``calls == []``: a
forged state must be rejected **before** any request leaves the server.

.. code-block:: text

   $ # (continued: the same run as the authorization matrix above)
   tests/integration/test_github_oauth.py::test_login_redirects_to_github_with_state PASSED [ 76%]
   tests/integration/test_github_oauth.py::test_callback_creates_user_and_returns_tokens PASSED [ 80%]
   tests/integration/test_github_oauth.py::test_second_login_finds_same_user PASSED [ 84%]
   tests/integration/test_github_oauth.py::test_callback_rejects_wrong_state PASSED [ 88%]
   tests/integration/test_github_oauth.py::test_callback_rejects_missing_state_cookie PASSED [ 92%]
   tests/integration/test_github_oauth.py::test_callback_handles_github_error_in_200_body PASSED [ 96%]
   tests/integration/test_github_oauth.py::test_github_not_configured_returns_503 PASSED [100%]

-----

The Whole Suite
----------------

.. code-block:: text

   $ make coverage
   ...
   Name                                 Stmts   Miss Branch BrPart  Cover   Missing
   --------------------------------------------------------------------------------
   src/bookshelf/auth/config.py            28      0      4      0   100%
   src/bookshelf/auth/dependencies.py      25      0      4      0   100%
   src/bookshelf/auth/github.py            35      1      2      0    97%   25
   src/bookshelf/auth/passwords.py         11      0      2      0   100%
   src/bookshelf/auth/rate_limit.py        26      0      4      0   100%
   src/bookshelf/auth/service.py           66      2     12      2    95%   164, 168
   src/bookshelf/auth/tokens.py            30      2      2      0    94%   60-61
   src/bookshelf/database.py               42      1     10      1    96%   101
   src/bookshelf/isbn_service.py            6      0      0      0   100%
   src/bookshelf/main.py                   29      0      0      0   100%
   src/bookshelf/manage.py                 21      1      6      1    93%   33
   src/bookshelf/models.py                 64      0      6      0   100%
   src/bookshelf/routers/auth.py           78      1     10      1    98%   143
   src/bookshelf/routers/books.py          45      0      6      0   100%
   src/bookshelf/routers/reviews.py        20      0      4      0   100%
   src/bookshelf/services.py               52      1     10      1    97%   74
   --------------------------------------------------------------------------------
   TOTAL                                  578      9     82      6    98%
   Coverage XML written to file coverage.xml
   Required test coverage of 80.0% reached. Total coverage: 97.73%
   ======================== 163 passed, 1 warning in 4.60s ========================

   $ make test-pg 2>&1 | grep passed
   ======================= 163 passed, 1 warning in 12.36s ========================

From 80 tests in Chapter 5 to 163, still under 5 seconds on SQLite. The suite runs
unchanged on PostgreSQL. ``github.py`` line 25 is the real ``httpx.Client``
constructor, the one line the tests replace on purpose.

The CI workflow from Chapter 5 needs **no changes**: no new secrets, no new services.
The same ``make coverage`` and ``make test-pg`` run there.

-----

**Exercises**

#. Add ``make_token``, ``auth_headers``, ``admin_headers``, ``auth_client`` and
   ``admin_client`` to ``tests/integration/conftest.py`` (copy from
   ``support/test-auth-fixtures.py``), and update the ``create_book`` fixture to send
   ``auth_headers``. Make the Chapter 5 tests in ``test_books_api.py`` and
   ``test_reviews_api.py`` pass again. Then write ``test_authz.py`` with tests for:
   unauthenticated access (401), insufficient role (403), expired token (401),
   tampered token (401), and valid access (200/201/204).

#. Write ``test_github_oauth.py`` with a ``MockTransport``-based fake GitHub. Cover: a
   new user is created on first login, the **same** user is found on a second login,
   a wrong ``state`` is rejected without contacting GitHub, and GitHub's
   ``200 {"error": ...}`` response becomes a 400. Add one more: a GitHub user who renames
   their account (same ``id``, new ``login``) still maps to the same local user.

#. Rewrite ``test_user_can_create_book`` using the ``as_admin`` dependency override.
   Then break ``decode_access_token`` on purpose (make it ignore ``exp``). Which of the
   two versions of the test notices? Which tests in the suite catch the bug?

#. Count how long the suite would take if every test logged in through
   ``/auth/login``: measure one Argon2 verification (``python -c`` with ``timeit``),
   count the tests that send a token (``grep -c``), and multiply. Compare with the
   measured suite time. Then explain why ``test_auth_api.py`` still logs in for real.
