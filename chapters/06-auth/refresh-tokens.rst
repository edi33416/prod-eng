.. _ch06_refresh_tokens:

Refresh Token Flow
===================

Tokens That Could Not Be Taken Back Fast Enough
------------------------------------------------

On 12 April 2022, GitHub's security team noticed that someone was using OAuth tokens
issued to two of GitHub's integration partners, **Heroku** and **Travis CI**, to list and
download private repositories of dozens of organizations, npm among them. The attacker
had stolen the tokens from the partners' systems, not from GitHub. The tokens were
genuine and correctly signed, so to GitHub every request looked legitimate.

The response was revocation. GitHub, Heroku and Travis CI revoked the affected tokens,
and Heroku turned off its GitHub integration for weeks while it rebuilt it. Revoking
worked because those tokens were **looked up on the server** on every use. A purely
self-contained token that lived for months would have kept working until it expired.

The BookShelf access token cannot be revoked, so we keep it to 15 minutes. That creates
the opposite problem: nobody wants to type a password every 15 minutes. A refresh token
keeps the convenience and gives back the revocation.

-----

The Flow
---------

.. code-block:: text

   Client                                              BookShelf API
     │ POST /auth/login                                      │
     │──────────────────────────────────────────────────────▶│
     │ {access_token (15 min), refresh_token (7 days)}       │ store hash(refresh)
     │◀──────────────────────────────────────────────────────│
     │                                                       │
     │ GET /auth/me   Authorization: Bearer <access>         │
     │──────────────────────────────────────────────────────▶│ verify signature only
     │ ... 15 minutes later ...                              │
     │ 401 {"detail": "Token expired"}                       │
     │◀──────────────────────────────────────────────────────│
     │                                                       │
     │ POST /auth/refresh {refresh_token}                    │
     │──────────────────────────────────────────────────────▶│ look up hash, check
     │ {new access_token, NEW refresh_token}                 │ revoke old, store new
     │◀──────────────────────────────────────────────────────│
     │                                                       │
     │ POST /auth/logout {refresh_token}                     │
     │──────────────────────────────────────────────────────▶│ revoke
     │ 204                                                   │

Every request costs a signature check except ``/auth/refresh``, which costs one database
lookup every 15 minutes per active user. That is the compromise: stateless where it is
hot, stateful where it matters.

-----

Design Decisions
-----------------

**An opaque random string, not a JWT.**
   The server has to look the token up anyway to check whether it was revoked. A
   signature would add size and nothing else. ``secrets.token_urlsafe(32)`` gives 256
   bits of randomness.

**Only the hash is stored.**
   The ``refresh_tokens`` table holds ``sha256(token)``. Someone who reads the database
   (a backup, a SQL injection, a curious colleague) gets nothing they can present to
   ``/auth/refresh``. A fast hash is fine here, unlike for passwords: the input is 256
   random bits, so there is nothing to guess.

**Rotation: every refresh token works once.**
   ``/auth/refresh`` revokes the token it receives and returns a new one along with the
   new access token.

**Reuse detection.**
   If a token that was **already used** comes back, either the client has a bug or the
   token was copied by someone else. The server cannot tell which, so it revokes
   **every** refresh token of that user. The thief loses access, and the real user loses
   access too and logs in again. That is far cheaper than a session the attacker keeps.

.. code-block:: python

   refresh_tokens = Table(
       "refresh_tokens",
       metadata,
       Column("id", Integer, primary_key=True),
       Column(
           "user_id",
           Integer,
           ForeignKey("users.id", ondelete="CASCADE"),
           nullable=False,
       ),
       # SHA-256 of the token. The token itself is never stored.
       Column("token_hash", String(64), nullable=False, unique=True),
       # Unix timestamps: portable across SQLite and PostgreSQL.
       Column("expires_at", BigInteger, nullable=False),
       Column("revoked", Boolean, nullable=False, server_default=false()),
   )

Expiry is a Unix timestamp in a ``BigInteger`` column, not a ``DateTime``. SQLite stores
datetimes as text and returns them without a timezone, while PostgreSQL returns aware
datetimes. Comparing integers works the same on both engines, the lesson from Chapter
4's ``LOWER() LIKE``.

-----

Implementation
---------------

The service layer (``auth/service.py``):

.. code-block:: python

   def issue_refresh_token(conn: Connection, user_id: int, ttl_days: int) -> str:
       token, token_hash = new_refresh_token()
       conn.execute(
           text(
               "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) "
               "VALUES (:user_id, :token_hash, :expires_at)"
           ),
           {
               "user_id": user_id,
               "token_hash": token_hash,
               "expires_at": int(time.time()) + ttl_days * 86400,
           },
       )
       conn.commit()
       return token


   def rotate_refresh_token(
       conn: Connection, token: str, ttl_days: int
   ) -> tuple[UserRecord, str] | None:
       row = (
           conn.execute(
               text(
                   "SELECT id, user_id, expires_at, revoked FROM refresh_tokens "
                   "WHERE token_hash = :token_hash"
               ),
               {"token_hash": hash_refresh_token(token)},
           )
           .mappings()
           .first()
       )
       if row is None:
           return None
       if row["revoked"]:
           revoke_all_refresh_tokens(conn, row["user_id"])
           return None
       if row["expires_at"] < time.time():
           return None

       # Conditional UPDATE: of two concurrent requests with the same token,
       # only one can flip revoked from false to true.
       result = conn.execute(
           text(
               "UPDATE refresh_tokens SET revoked = true "
               "WHERE id = :id AND revoked = false"
           ),
           {"id": row["id"]},
       )
       conn.commit()
       if result.rowcount != 1:
           return None

       user = get_user_by_id(conn, row["user_id"])
       if user is None:
           return None
       return user, issue_refresh_token(conn, user.id, ttl_days)

Look at the conditional ``UPDATE``. A ``SELECT``, then a check in Python, then an
unconditional ``UPDATE`` would let two simultaneous requests with the same token both
pass the check and both receive new tokens. Putting the condition in the ``UPDATE``
makes the database the referee: exactly one request sees ``rowcount == 1``. This is the
same compare-and-set idea you know from concurrent programming, done in SQL.

The endpoints (``routers/auth.py``):

.. code-block:: python

   @router.post("/refresh", response_model=TokenResponse)
   def refresh(body: RefreshRequest) -> TokenResponse:
       settings = get_settings()
       with get_connection() as conn:
           rotated = auth_service.rotate_refresh_token(
               conn, body.refresh_token, settings.refresh_token_days
           )
           if rotated is None:
               raise HTTPException(status_code=401, detail="Invalid refresh token")
           user, new_refresh = rotated
           # The user is re-read from the database, so a role change or a
           # deleted account takes effect here, at the latest one access-token
           # lifetime after it happened.
           return TokenResponse(
               access_token=create_access_token(user.as_current_user()),
               refresh_token=new_refresh,
               expires_in=settings.access_token_minutes * 60,
           )


   @router.post("/logout", status_code=204)
   def logout(body: RefreshRequest) -> None:
       with get_connection() as conn:
           auth_service.revoke_refresh_token(conn, body.refresh_token)

``/auth/refresh`` does not require an access token. Its whole purpose is to work after
the access token has expired. The refresh token **is** the credential.

-----

Watching It Work
-----------------

Continuing from :ref:`ch06_implementing_jwt`, Alice was promoted to admin. She logs in
again, gets a token that says ``admin``, and is then demoted:

.. code-block:: bash

   $ curl -s localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
   {"id":1,"username":"alice","role":"admin"}

   $ docker compose exec api python -m bookshelf.manage demote alice
   alice is now user
   $ curl -s localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
   {"id":1,"username":"alice","role":"admin"}

The access token still says ``admin``. Refresh:

.. code-block:: bash

   $ curl -s -X POST localhost:8000/auth/refresh -H 'Content-Type: application/json' \
       -d "{\"refresh_token\": \"$REFRESH\"}" | jq .
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJhbGljZSIsInJvbGUiOiJ1c2VyIiwiaXNzIjoiYm9va3NoZWxmIiwiYXVkIjoiYm9va3NoZWxmLWFwaSIsImlhdCI6MTc5NDQ4NTM2NCwiZXhwIjoxNzk0NDg2MjY0fQ.FlKPjcPHHR-Ot6JhD44QqZ9FEV4AO7BrD0QG4iE5yzA",
     "refresh_token": "GBEfsibmy-Nx3rpIJ66Yy2Z68If876v93OqlE2zXc8Y",
     "token_type": "bearer",
     "expires_in": 900
   }
   $ curl -s localhost:8000/auth/me -H "Authorization: Bearer $NEW_TOKEN"
   {"id":1,"username":"alice","role":"user"}

Now present the **old** refresh token a second time, as a thief who copied it would:

.. code-block:: bash

   $ curl -si -X POST localhost:8000/auth/refresh -H 'Content-Type: application/json' \
       -d "{\"refresh_token\": \"$REFRESH\"}"
   HTTP/1.1 401 Unauthorized
   ...
   {"detail":"Invalid refresh token"}

   $ curl -s -X POST localhost:8000/auth/refresh -H 'Content-Type: application/json' \
       -d "{\"refresh_token\": \"$NEW_REFRESH\"}"
   {"detail":"Invalid refresh token"}

The reuse also killed the token Alice received a moment ago. In the database:

.. code-block:: text

   $ docker compose exec db psql -U bookshelf -d bookshelf -c \
       "SELECT id, user_id, left(token_hash, 16) AS token_hash, expires_at, revoked
        FROM refresh_tokens ORDER BY id;"
    id | user_id |    token_hash    | expires_at | revoked
   ----+---------+------------------+------------+---------
     1 |       1 | a8874e1485e398eb | 1795090125 | t
     2 |       1 | 6aff8d0d0b447c77 | 1795090163 | t
     3 |       1 | 6ad2b4b87282e415 | 1795090164 | t
   (3 rows)

Only hashes, all revoked. Logout is the polite version of the same thing:

.. code-block:: bash

   $ curl -si -X POST localhost:8000/auth/logout -H 'Content-Type: application/json' \
       -d "{\"refresh_token\": \"$R\"}" | head -1
   HTTP/1.1 204 No Content
   $ curl -s -X POST localhost:8000/auth/refresh -H 'Content-Type: application/json' \
       -d "{\"refresh_token\": \"$R\"}"
   {"detail":"Invalid refresh token"}

.. admonition:: Observation:

   Logout revokes the refresh token, **not** the access token, which stays valid for up
   to 15 more minutes. A client deletes it locally, but a copy elsewhere keeps working.
   If that is unacceptable, you need a deny-list of access-token ``jti`` values checked
   on every request, typically in Redis (already in the Compose stack). Then the access
   token is no longer stateless, and you should ask whether a session store would have
   been simpler.

-----

Where Does the Client Keep the Refresh Token?
----------------------------------------------

The BookShelf API returns tokens in the JSON body, which suits ``curl``, mobile apps and
server-side clients. A browser application has a harder choice:

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - Storage
     - Risk
     - Notes
   * - ``localStorage``
     - Any JavaScript on the page can read it, including an injected script (XSS)
     - Simple, and the most common mistake
   * - JavaScript memory
     - Lost on page reload
     - Fine for the access token
   * - ``HttpOnly; Secure; SameSite=Strict`` cookie
     - JavaScript cannot read it. The browser sends it automatically, which opens CSRF
       unless ``SameSite`` and the cookie path are restrictive
     - The usual recommendation for the refresh token, with ``Path=/auth/refresh``

A common browser setup: access token in memory, refresh token in an ``HttpOnly`` cookie
scoped to ``/auth/refresh``. On page load the app calls ``/auth/refresh`` to get a fresh
access token. Exercise 3 below implements the cookie variant.

-----

**Exercises**

#. Implement ``issue_refresh_token``, ``rotate_refresh_token``,
   ``revoke_refresh_token``, ``revoke_all_refresh_tokens`` and the ``/auth/refresh`` and
   ``/auth/logout`` endpoints until ``tests/unit/test_auth_service.py`` and the refresh
   tests in ``test_auth_api.py`` pass. Then run the full flow by hand with
   ``ACCESS_TOKEN_EXPIRE_MINUTES=1``: login → use access token → wait for it to expire →
   refresh → use the new access token → logout → refresh fails with 401.

#. Draw a timeline of two requests, A and B, that call ``/auth/refresh`` with the same
   token at the same moment. Each step is one SQL statement: A ``SELECT``, B
   ``SELECT``, A ``UPDATE``, B ``UPDATE``. Do it once with the conditional ``UPDATE`` and
   once with ``AND revoked = false`` removed. How many new refresh tokens exist at the
   end of each version? Then reproduce the interleaving in a test with two connections
   from the ``db_engine`` fixture, issuing the four statements by hand in that order.

#. Add a cookie variant: when the request header ``X-Client: browser`` is present,
   ``/auth/login`` and ``/auth/refresh`` set the refresh token as an ``HttpOnly``,
   ``Secure`` (from ``COOKIE_SECURE``), ``SameSite=Strict`` cookie with
   ``Path=/auth/refresh`` instead of returning it in the body, and ``/auth/refresh``
   reads it from the cookie. Write integration tests for both variants.

#. The ``refresh_tokens`` table only grows. Write a ``python -m bookshelf.manage
   purge-tokens`` command that deletes rows that are revoked or expired, and print how
   many were removed. Why is deleting revoked tokens immediately after use a bad idea?
   (Hint: reuse detection.)
