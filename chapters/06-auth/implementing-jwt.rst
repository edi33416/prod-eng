.. _ch06_implementing_jwt:

JWT Authentication for the BookShelf API
=========================================

.. note::

   Work in ``support/bookshelf-ch6/``. The functions you implement on this page are
   stubs in ``src/bookshelf/auth/`` and ``src/bookshelf/routers/auth.py``. Their tests
   are already there:

   .. code-block:: bash

      $ cd support/bookshelf-ch6
      $ python -m venv .venv && source .venv/bin/activate
      $ pip install -r requirements-dev.lock && pip install --no-deps -e .
      $ pytest -q 2>&1 | tail -1
      =================== 36 failed, 98 passed, 1 warning in 4.71s ===================

   The 36 failures are your to-do list for this page and the next two:
   ``tests/unit/test_passwords.py``, ``test_tokens.py``, ``test_auth_service.py``,
   ``test_rate_limit.py`` and ``tests/integration/test_auth_api.py``.

-----

Copying the Tutorial
---------------------

Most FastAPI authentication tutorials written before 2025 start like this:

.. code-block:: python

   from passlib.context import CryptContext

   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

Install ``passlib`` and today's ``bcrypt`` and try to hash a password:

.. code-block:: text

   $ pip install passlib==1.7.4 bcrypt==5.0.0
   $ python -c "
   from passlib.context import CryptContext
   pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
   print(pwd_context.hash('correct horse battery staple'))"
   (trapped) error reading bcrypt version
   Traceback (most recent call last):
     ...
   AttributeError: module 'bcrypt' has no attribute '__about__'
   Traceback (most recent call last):
     ...
     File ".../passlib/handlers/bcrypt.py", line 655, in _calc_checksum
       hash = _bcrypt.hashpw(secret, config)
   ValueError: password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])

The password is 28 bytes. The crash comes from passlib's start-up self-test, which hashes
a 255-byte string to detect an old bcrypt bug. Recent ``bcrypt`` versions refuse inputs
over 72 bytes instead of silently truncating them. passlib's last release, 1.7.4, is from
October 2020. Nobody is coming to fix it.

Code that handles passwords is security-critical, and security-critical dependencies
must be **maintained**. The BookShelf API uses ``pwdlib``, written by the maintainer of
FastAPI Users and now used in FastAPI's own documentation, with the **Argon2id**
algorithm. The crash course in :ref:`ch06_security_best_practices` explains why Argon2id
and not SHA-256.

.. admonition:: Observation:

   A crash at start-up is the friendly way for a dependency to rot. The dangerous way is
   a library that keeps working and quietly stops being safe. Chapter 5's Dependabot
   watches GitHub Actions and Docker images. Chapter 10 extends that watch to Python
   packages, with vulnerability scanning.

-----

Step 1: The Signing Secret
---------------------------

Every token's security rests on one value, ``JWT_SECRET_KEY``. Configuration lives in
``auth/config.py`` (complete in the starter):

.. code-block:: python

   @lru_cache
   def get_settings() -> AuthSettings:
       secret = os.getenv("JWT_SECRET_KEY", "")
       if len(secret) < MIN_SECRET_LENGTH:
           raise ConfigError(
               f"JWT_SECRET_KEY must be set to at least {MIN_SECRET_LENGTH} characters. "
               ...
           )
       return AuthSettings(jwt_secret_key=secret, jwt_algorithm="HS256", ...)

``main.py`` calls ``get_settings()`` in the lifespan hook, so a container without a
secret refuses to start. This is the fail-fast pattern from Chapter 4's
``DATABASE_URL``:

.. code-block:: text

   $ docker build -q -t bookshelf:0.6.0 . && docker run --rm bookshelf:0.6.0
   ...
   bookshelf.auth.config.ConfigError: JWT_SECRET_KEY must be set to at least 32 characters. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"

   ERROR:    Application startup failed. Exiting.

The alternative, a default like ``SECRET_KEY = "changeme"`` in the code, means some
deployment eventually runs with it, and then anyone who has read your repository can
mint admin tokens for it.

Generate a secret and put it in ``.env`` (gitignored since Chapter 4):

.. code-block:: bash

   $ cp .env.example .env
   $ python -c "import secrets; print(secrets.token_urlsafe(32))"
   BpyMnBTrOK7_DgzjWG8aASgenSiNSzD07vuu2wnSQXg

``docker-compose.yml`` passes it to the ``api`` container and, like
``POSTGRES_PASSWORD``, refuses to start without it:

.. code-block:: yaml

   JWT_SECRET_KEY: ${JWT_SECRET_KEY:?Set JWT_SECRET_KEY in .env}

.. warning::

   Never hardcode the secret, never commit it, never log it, and never reuse the same
   secret in development, staging and production. A token signed in staging would then
   be valid in production. For the GitHub Actions side of secret handling, see
   :ref:`ch05_secrets_environments`. CI does **not** need this secret: the test suite
   sets its own (:ref:`ch06_testing_auth`).

-----

Step 2: Hashing Passwords
--------------------------

The ``users`` table is in ``database.py``:

.. code-block:: python

   users = Table(
       "users",
       metadata,
       Column("id", Integer, primary_key=True),
       Column("username", String(64), nullable=False, unique=True),
       # NULL for accounts that only ever log in through GitHub.
       Column("password_hash", Text, nullable=True),
       Column("role", String(16), nullable=False, server_default="user"),
       Column("github_id", BigInteger, nullable=True, unique=True),
       Column("email", Text, nullable=True),
       CheckConstraint("role IN ('user', 'admin')", name="role_valid"),
   )

There is a ``password_hash`` column and no ``password`` column. Implement
``auth/passwords.py``:

.. code-block:: python

   from pwdlib import PasswordHash
   from pwdlib.hashers.argon2 import Argon2Hasher

   _hasher = PasswordHash((Argon2Hasher(),))

   # Compared against when the username does not exist, so that a failed login
   # takes the same time whether or not the account exists.
   _DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


   def hash_password(password: str) -> str:
       return _hasher.hash(password)


   def verify_password(password: str, password_hash: str | None) -> bool:
       if password_hash is None:
           _hasher.verify(password, _DUMMY_HASH)
           return False
       return _hasher.verify(password, password_hash)

The hash records everything needed to verify it later:

.. code-block:: text

   $argon2id$v=19$m=65536,t=3,p=4$hWqlbFvun...$...
    └─algo──┘ └ver┘ └─cost: 64 MiB, 3 passes, 4 lanes─┘ └salt┘ └hash┘

The **salt** is random per hash, so two users with the same password get different
hashes. Because the cost parameters are stored in the hash, you can raise them later
without breaking existing passwords.

Why bother with ``_DUMMY_HASH``? Verifying an Argon2 hash takes time on purpose:

.. code-block:: text

   verify: 66 ms              # one Argon2id verification
   sha256 x1e6: 698 ms        # one million SHA-256 hashes

If the login code returned at once for an unknown username but spent 66 ms on a known
one, an attacker could time responses to learn which usernames exist. Doing the same
work in both cases removes that signal.

.. code-block:: bash

   $ pytest tests/unit/test_passwords.py -q 2>&1 | tail -1
   ============================== 5 passed in 0.67s ===============================

-----

Step 3: Registration
---------------------

Request and response models (in ``models.py``):

.. code-block:: python

   class UserCreate(BaseModel):
       username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_-]+$")
       # SecretStr prints as '**********' in reprs, logs and tracebacks.
       password: SecretStr

       @field_validator("password")
       @classmethod
       def validate_password_length(cls, v: SecretStr) -> SecretStr:
           if not 12 <= len(v.get_secret_value()) <= 128:
               raise ValueError("Password must be between 12 and 128 characters")
           return v


   class UserResponse(BaseModel):
       id: int
       username: str
       role: str

There is no ``role`` field in ``UserCreate`` and no ``password`` field in
``UserResponse``. The endpoint:

.. code-block:: python

   @router.post("/register", response_model=UserResponse, status_code=201)
   def register(body: UserCreate) -> UserResponse:
       with get_connection() as conn:
           try:
               user = auth_service.create_user(
                   conn, body.username, hash_password(body.password.get_secret_value())
               )
           except IntegrityError:
               raise HTTPException(
                   status_code=409, detail="Username already taken"
               ) from None
       return UserResponse(id=user.id, username=user.username, role=user.role)

``auth_service.create_user`` (complete in the starter) always inserts ``role = 'user'``.
Try it against the running stack (``docker compose up -d --build``):

.. code-block:: bash

   $ curl -si -X POST localhost:8000/auth/register \
       -H 'Content-Type: application/json' \
       -d '{"username": "alice", "password": "correct horse battery staple"}'
   HTTP/1.1 201 Created
   date: Thu, 12 Nov 2026 12:08:44 GMT
   server: uvicorn
   content-length: 41
   content-type: application/json
   vary: Origin

   {"id":1,"username":"alice","role":"user"}

   $ curl -s -X POST localhost:8000/auth/register \
       -H 'Content-Type: application/json' \
       -d '{"username": "mallory", "password": "i am definitely an admin", "role": "admin"}'
   {"id":2,"username":"mallory","role":"user"}

Pydantic ignores the unknown ``role`` field, and Mallory is a ``user``.

.. admonition:: Observation:

   In March 2012, Egor Homakov added his SSH key to the ``rails/rails`` organization on
   GitHub and pushed a commit to the Rails repository itself. GitHub's Rails code
   copied every request parameter into the model being updated ("mass assignment"),
   including the field that says which user a key belongs to. **Never build a database
   row from the request body wholesale.** Declare exactly the fields a client may set.
   Here that is ``UserCreate``, and ``role`` is not one of them.

So how does anyone become an admin? Not over HTTP. ``bookshelf/manage.py`` is a small
command-line tool that runs where the database is:

.. code-block:: bash

   $ docker compose exec api python -m bookshelf.manage promote alice
   alice is now admin

Anyone who can run commands inside the container already controls the service, so the
tool adds no new attack surface. An HTTP endpoint for "make me admin" would.

A Finding: the Password in the Error Message
"""""""""""""""""""""""""""""""""""""""""""""

While building this chapter, the first version of ``UserCreate`` used ``password: str =
Field(min_length=12)``. Registering with a short password returned:

.. code-block:: json

   {
     "detail": [
       {
         "type": "string_too_short",
         "loc": ["body", "password"],
         "msg": "String should have at least 12 characters",
         "input": "hunter2",
         "ctx": {"min_length": 12}
       }
     ]
   }

FastAPI's default 422 response **echoes the rejected value**. For a password that
nearly passed (one character too short, a typo of the real one), that puts the
password into browser developer tools, client-side error logging, and any proxy or
gateway that records response bodies. ``SecretStr`` alone does not help: Pydantic still
reports the raw input. The solution's ``main.py`` replaces the 422 handler for the whole
app:

.. code-block:: python

   @app.exception_handler(RequestValidationError)
   async def validation_error_handler(
       request: Request, exc: RequestValidationError
   ) -> JSONResponse:
       # FastAPI's default 422 body echoes the rejected value back ("input").
       # For a too-short password that is the password itself, which then
       # ends up in client logs, proxies and error trackers. Drop it.
       errors = [
           {k: v for k, v in error.items() if k != "input"} for error in exc.errors()
       ]
       return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})

.. code-block:: bash

   $ curl -s -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
       -d '{"username": "bob", "password": "hunter2"}' | jq .
   {
     "detail": [
       {
         "type": "value_error",
         "loc": [
           "body",
           "password"
         ],
         "msg": "Value error, Password must be between 12 and 128 characters",
         "ctx": {
           "error": {}
         }
       }
     ]
   }

``test_validation_error_does_not_echo_password`` guards against a regression.

-----

Step 4: Login and Token Creation
---------------------------------

``auth/tokens.py`` turns a user into a signed token and back. ``CurrentUser`` is what
the rest of the app sees: an immutable value built from the token's claims.

.. code-block:: python

   @dataclass(frozen=True)
   class CurrentUser:
       id: int
       username: str
       role: str


   def create_access_token(
       user: CurrentUser, expires_delta: timedelta | None = None
   ) -> str:
       settings = get_settings()
       now = datetime.now(UTC)
       if expires_delta is None:
           expires_delta = timedelta(minutes=settings.access_token_minutes)
       payload = {
           "sub": str(user.id),
           "username": user.username,
           "role": user.role,
           "iss": settings.jwt_issuer,
           "aud": settings.jwt_audience,
           "iat": now,
           "exp": now + expires_delta,
       }
       return jwt.encode(
           payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
       )


   def decode_access_token(token: str) -> CurrentUser:
       settings = get_settings()
       payload = jwt.decode(
           token,
           settings.jwt_secret_key,
           # A fixed list: never trust the "alg" field of the token itself.
           algorithms=[settings.jwt_algorithm],
           issuer=settings.jwt_issuer,
           audience=settings.jwt_audience,
           options={"require": ["sub", "exp", "iat", "iss", "aud"]},
       )
       try:
           return CurrentUser(
               id=int(payload["sub"]),
               username=str(payload["username"]),
               role=str(payload["role"]),
           )
       except (KeyError, ValueError) as exc:
           raise jwt.InvalidTokenError("Malformed claims") from exc

Use ``datetime.now(UTC)``, not ``datetime.utcnow()``. The latter is deprecated since
Python 3.12 and returns a naive datetime, a classic source of tokens that expire hours
early or late on servers outside UTC. ``options={"require": [...]}`` matters too.
Without it, a token with **no** ``exp`` claim is accepted and never expires.

The login endpoint:

.. code-block:: python

   @router.post(
       "/login",
       response_model=TokenResponse,
       dependencies=[Depends(login_rate_limit)],
   )
   def login(body: LoginRequest) -> TokenResponse:
       with get_connection() as conn:
           user = auth_service.get_user_by_username(conn, body.username)
           # Same message, and the same amount of hashing work, whether the user
           # does not exist or the password is wrong.
           password_hash = user.password_hash if user else None
           password = body.password.get_secret_value()
           if not verify_password(password, password_hash) or user is None:
               raise HTTPException(status_code=401, detail="Invalid credentials")
           return _issue_tokens(conn, user)

(``login_rate_limit`` is a no-op in the starter until
:ref:`ch06_security_best_practices`; ``_issue_tokens`` also creates the refresh token
from :ref:`ch06_refresh_tokens`.)

.. code-block:: bash

   $ curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
       -d '{"username": "alice", "password": "correct horse battery staple"}' | jq .
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJhbGljZSIsInJvbGUiOiJ1c2VyIiwiaXNzIjoiYm9va3NoZWxmIiwiYXVkIjoiYm9va3NoZWxmLWFwaSIsImlhdCI6MTc5NDQ4NTMyNSwiZXhwIjoxNzk0NDg2MjI1fQ.jOEEQ9yso8N8Yd7SqCNn6wAL7WehFup7x9AFEzclJAk",
     "refresh_token": "wG4BBCAmn0vI-JxZ7jJeAXsZbVxTm8HvtiMX39Gq3DY",
     "token_type": "bearer",
     "expires_in": 900
   }

   $ curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
       -d '{"username": "alice", "password": "wrong"}'
   {"detail":"Invalid credentials"}

   $ curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
       -d '{"username": "nobody", "password": "wrong"}'
   {"detail":"Invalid credentials"}

Decode the access token's payload (exercise 1 of :ref:`ch06_jwt_fundamentals`) and you
will find ``{"sub":"1","username":"alice","role":"user","iss":"bookshelf",
"aud":"bookshelf-api","iat":1794485325,"exp":1794486225}``: 900 seconds, 15 minutes.

-----

Step 5: Protecting Endpoints
-----------------------------

A FastAPI **dependency** runs before the endpoint and can reject the request. Implement
``auth/dependencies.py``:

.. code-block:: python

   # auto_error=False: we raise our own 401 (with the WWW-Authenticate header
   # RFC 6750 asks for) instead of relying on the library's default.
   _bearer = HTTPBearer(auto_error=False)


   def _unauthorized(detail: str) -> HTTPException:
       return HTTPException(
           status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
       )


   def get_current_user(
       credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
   ) -> CurrentUser:
       if credentials is None:
           raise _unauthorized("Not authenticated")
       try:
           return decode_access_token(credentials.credentials)
       except jwt.ExpiredSignatureError:
           raise _unauthorized("Token expired") from None
       except jwt.InvalidTokenError:
           raise _unauthorized("Invalid token") from None


   AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]

``HTTPBearer`` extracts the token from ``Authorization: Bearer <token>``. It also adds an
**Authorize** button to the Swagger UI at ``/docs``: paste an access token there, and
every "Try it out" request sends it.

Attach the dependency to the write endpoints in ``routers/books.py``:

.. code-block:: python

   @router.post(
       "/",
       response_model=BookResponse,
       status_code=201,
       dependencies=[Depends(get_current_user)],
   )
   def create_book_endpoint(book: BookCreate) -> BookResponse:
       ...

``dependencies=[...]`` runs the check without passing the user to the function. When the
endpoint needs to know **who** is calling, declare a parameter instead, as the reviews
endpoint does below.

.. code-block:: bash

   $ curl -si -X POST localhost:8000/books/ -H 'Content-Type: application/json' \
       -d '{"title": "Clean Code", "author": "Robert Martin", "isbn": "9780132350884", "year": 2008}'
   HTTP/1.1 401 Unauthorized
   date: Thu, 12 Nov 2026 12:08:44 GMT
   server: uvicorn
   www-authenticate: Bearer
   content-length: 30
   content-type: application/json
   vary: Origin

   {"detail":"Not authenticated"}

   $ TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUi...
   $ curl -s -X POST localhost:8000/books/ -H 'Content-Type: application/json' \
       -H "Authorization: Bearer $TOKEN" \
       -d '{"title": "Clean Code", "author": "Robert Martin", "isbn": "9780132350884", "year": 2008}'
   {"id":1,"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008}

Now run the Chapter 5 integration tests against the protected API:

.. code-block:: text

   $ pytest tests/integration/test_books_api.py -q --tb=line
   ...
   =========================== short test summary info ============================
   FAILED tests/integration/test_books_api.py::test_create_book_returns_201 - assert ...
   FAILED tests/integration/test_books_api.py::test_get_book_returns_200 - KeyError: ...
   FAILED tests/integration/test_books_api.py::test_list_books_returns_created_books
   FAILED tests/integration/test_books_api.py::test_update_book_changes_title - Asser...
   FAILED tests/integration/test_books_api.py::test_delete_book_removes_it - Assertio...
   FAILED tests/integration/test_books_api.py::test_search_books_by_title - assert 0 ...
   FAILED tests/integration/test_books_api.py::test_top_books_returns_correct_order
   FAILED tests/integration/test_books_api.py::test_list_books_pagination - assert 0 ...
   FAILED tests/integration/test_books_api.py::test_create_duplicate_isbn_returns_409
   FAILED tests/integration/test_books_api.py::test_create_book_invalid_isbn_returns_422
   FAILED tests/integration/test_books_api.py::test_update_nonexistent_book_returns_404
   FAILED tests/integration/test_books_api.py::test_delete_nonexistent_book_returns_404
   FAILED tests/integration/test_books_api.py::test_book_review_full_flow - KeyError:...
   =================== 13 failed, 2 passed, 1 warning in 0.30s ===================

That is the point of the change, not a regression. Look at
``test_create_book_invalid_isbn_returns_422``: it now gets 401, not 422. FastAPI runs the
auth dependency before it reports body validation errors, so an anonymous client cannot
even probe which inputs are valid. :ref:`ch06_testing_auth` fixes the tests without
making every test log in.

-----

Step 6: Roles
--------------

Authorization is a second dependency that builds on the first:

.. code-block:: python

   def require_role(role: str) -> Callable[[CurrentUser], CurrentUser]:
       def checker(
           user: Annotated[CurrentUser, Depends(get_current_user)],
       ) -> CurrentUser:
           if user.role != role:
               raise HTTPException(status_code=403, detail="Insufficient permissions")
           return user

       return checker

.. code-block:: python

   @router.delete(
       "/{book_id}", status_code=204, dependencies=[Depends(require_role("admin"))]
   )
   def delete_book_endpoint(book_id: int) -> None:
       ...

.. code-block:: bash

   $ curl -si -X DELETE localhost:8000/books/1 -H "Authorization: Bearer $TOKEN"
   HTTP/1.1 403 Forbidden
   date: Thu, 12 Nov 2026 12:08:44 GMT
   server: uvicorn
   content-length: 37
   content-type: application/json
   vary: Origin

   {"detail":"Insufficient permissions"}

   $ docker compose exec api python -m bookshelf.manage promote alice
   alice is now admin
   $ curl -s -X DELETE localhost:8000/books/1 -H "Authorization: Bearer $TOKEN"
   {"detail":"Insufficient permissions"}

Alice is an admin in the database and still gets 403. Her token was issued when she was
a ``user``, and the server does not look at the database: that is what "stateless"
means. The token keeps saying ``user`` until it expires, at most 15 minutes. The next
page shows how a refresh picks up the new role. The same delay applies in the other
direction: a **demoted** admin keeps admin rights for up to one access-token lifetime.
That is the trade-off you accept for not hitting the database on every request, and the
reason access tokens must be short-lived.

-----

Step 7: The Reviewer Is the Token
----------------------------------

The opening scenario: a bot posts reviews signed ``"reviewer": "alice"``. Remove the
field from ``ReviewCreate`` and take the name from the token:

.. code-block:: python

   class ReviewCreate(BaseModel):
       # No "reviewer" field: the reviewer is the authenticated user, taken from
       # the token. Never let the client tell you who it is in the request body.
       rating: int = Field(ge=1, le=5, description="Star rating from 1 to 5")
       text: str

.. code-block:: python

   @router.post("/books/{book_id}/reviews", response_model=ReviewResponse, status_code=201)
   def add_review_endpoint(
       book_id: int, review: ReviewCreate, user: AuthenticatedUser
   ) -> ReviewResponse:
       with get_connection() as conn:
           result = services.add_review(conn, book_id, review, reviewer=user.username)
           ...

.. code-block:: bash

   $ curl -s -X POST localhost:8000/books/1/reviews -H 'Content-Type: application/json' \
       -H "Authorization: Bearer $TOKEN" \
       -d '{"rating": 5, "text": "Essential.", "reviewer": "robert-martin"}'
   {"id":1,"book_id":1,"rating":5,"text":"Essential.","reviewer":"alice"}

The ``reviewer`` column and the response shape are unchanged, so existing API clients
and the database schema keep working. The column is now filled from a verified source.
(``metadata.create_all`` only creates missing tables. It never alters existing ones, so
changing the ``reviews`` table itself would need a migration tool. Chapter 4 deferred
that decision, and it is still deferred.)

-----

**Exercises**

#. Implement ``hash_password``, ``verify_password``, ``create_access_token``,
   ``decode_access_token``, ``register`` and ``login`` until ``test_passwords.py``,
   ``test_tokens.py`` and the registration and login tests in ``test_auth_api.py`` pass.
   Protect ``POST``/``PUT`` on ``/books/`` and ``POST`` on reviews with
   ``get_current_user``, and leave every ``GET`` public. Then walk through the whole flow
   with ``curl``: register → login → call a protected endpoint without and with the
   token. Repeat it in the Swagger UI using the **Authorize** button.

#. Implement ``require_role`` and protect ``DELETE /books/{id}``. Register a second user,
   promote one of them with ``python -m bookshelf.manage promote``, and show that the
   ``user`` gets 403 and the admin (with a **fresh** token) gets 204.

#. Token expiry, two ways:

   - Set ``ACCESS_TOKEN_EXPIRE_MINUTES=1`` in ``.env``, restart the stack, log in, wait
     61 seconds and call ``/auth/me``. Confirm ``401 {"detail":"Token expired"}``.
   - The setting is in minutes, so for a 5-second token use the code directly:
     ``create_access_token(CurrentUser(1, "alice", "user"), timedelta(seconds=5))`` in a
     Python shell with the same ``JWT_SECRET_KEY`` exported. Wait 6 seconds and use it.

#. ``test_tokens.py::test_missing_exp_rejected`` passes only because of
   ``options={"require": [...]}``. Remove that option, run the test, and explain in one
   sentence what an attacker could do with a stolen token that had no ``exp``.

#. Without changing any code, could Mallory get admin rights by registering the username
   ``admin``? By sending ``"role": "admin"`` to ``PUT /books/1``? Explain each answer by
   pointing at the line of code that stops her.
