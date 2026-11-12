.. _ch06_auth_concepts:

Authentication vs Authorization
================================

.. note::

   This chapter starts from the BookShelf API at the end of Chapter 5. The starter in
   ``support/bookshelf-ch6/`` is the Chapter 5 solution plus:

   - the new dependencies (``pyjwt``, ``pwdlib[argon2]``) in ``pyproject.toml`` and both
     lockfiles
   - the ``users`` and ``refresh_tokens`` tables in ``database.py``
   - an ``auth/`` package where every function you will write is a stub marked
     ``TODO(ch6)``, plus the unit and integration tests that those stubs must pass

   ``support/bookshelf-ch6-solution/`` is the finished state: 163 tests, passing on
   SQLite and PostgreSQL. ``support/keycloak/`` holds the optional SSO lab, and
   ``support/test-auth-fixtures.py`` the reusable test fixtures from
   :ref:`ch06_testing_auth`.

   You need Docker (Chapter 4) and a **GitHub account** to create an OAuth App. Nothing
   in this chapter needs a domain name or a public server.

   If you build through the internal package index from
   :ref:`ch05_internal_package_index`, the lockfiles now list six new packages
   (``pyjwt``, ``pwdlib``, ``argon2-cffi``, ``argon2-cffi-bindings``, ``cffi``,
   ``pycparser``). The index has fallback disabled, so re-run ``populate.sh`` with the
   new ``requirements-dev.lock`` before the first ``docker compose build``.

-----

Ten Million Customers, No Password Required
--------------------------------------------

In September 2022, Optus, Australia's second-largest telecom operator, disclosed that an
attacker had downloaded the personal records of about **9.8 million** current and former
customers: names, dates of birth, phone numbers, and for millions of them passport or
driving licence numbers. No password was cracked and no server was broken into. An API
endpoint, reachable from the internet, returned customer records to **anyone who asked**.
The records had sequential identifiers, so "asking" meant counting upwards.

The BookShelf API has the same design today. Every endpoint is public:

.. code-block:: bash

   $ curl -s -X DELETE localhost:8000/books/1 -w '%{http_code}\n'
   204

Anyone can create, change and delete books. Anyone can post a review and type any name
into the ``reviewer`` field. When a bot starts posting hundreds of fake one-star reviews
signed ``"reviewer": "alice"``, there is nothing to block: no account, no identity, not
even a reliable way to tell the bot's reviews from Alice's.

This chapter fixes that. By the end, write endpoints need a token, deleting a book needs
an admin, and the reviewer of a review is whoever the token says it is.

-----

Two Questions
--------------

Every protected request has to answer two separate questions, in this order:

**Authentication (AuthN): who are you?**
   The client proves an identity: a password, a token, a certificate. Failure means
   **401 Unauthorized** (despite the name, the status code is about *authentication*).

**Authorization (AuthZ): are you allowed to do this?**
   Given a known identity, the server checks a rule: a role, a scope, an ownership
   check. Failure means **403 Forbidden**.

.. code-block:: text

   request ──▶ AuthN: valid token? ──no──▶ 401 Unauthorized
                     │ yes: user = alice, role = user
                     ▼
               AuthZ: may "user" DELETE /books/1? ──no──▶ 403 Forbidden
                     │ yes
                     ▼
                  handler runs

The distinction matters when you debug. A 401 says "I don't know who you are": the
token is missing, expired or forged. A 403 says "I know exactly who you are, and the
answer is no". Logging in again fixes a 401 and never fixes a 403.

.. admonition:: Observation:

   The two questions fail in different ways. Broken authentication usually fails
   loudly: nobody can log in. Broken authorization fails silently: everyone can still do
   everything, including things they should not. "Broken Access Control" has been number
   one in the OWASP Top 10 since 2021, ahead of injection.

-----

Common Mechanisms
------------------

.. list-table::
   :header-rows: 1
   :widths: 16 34 25 25

   * - Mechanism
     - How it works
     - Good for
     - Weak at
   * - API key
     - A long random string sent in a header. The server looks it up.
     - Server-to-server calls, scripts, metering
     - Identifying *users*; keys are long-lived and leak into code and logs
   * - Session cookie
     - The server stores session state and gives the browser a random session ID in a
       cookie.
     - Traditional server-rendered web apps
     - Many servers share the session store; non-browser clients
   * - JWT
     - A signed, self-contained token carrying claims (user ID, role, expiry). Any
       server with the key can verify it without a lookup.
     - APIs, mobile apps, microservices
     - Revocation: a valid token stays valid until it expires
   * - OAuth 2.0
     - A protocol for one application to get **delegated** access to a user's data on
       another service, without seeing the user's password.
     - "Log in with GitHub", third-party integrations
     - Not an authentication protocol by itself
   * - SSO
     - One login at an Identity Provider grants access to many applications. Built on
       OpenID Connect (on top of OAuth 2.0) or SAML.
     - Organizations with many internal apps
     - Adds a critical dependency: when the IdP is down, nobody logs in

These are not alternatives to choose one of. Real systems combine them. In this chapter
the BookShelf API ends up with three:

- **JWT** for every API request (:ref:`ch06_jwt_fundamentals`,
  :ref:`ch06_implementing_jwt`), plus **refresh tokens** so users do not log in every 15
  minutes (:ref:`ch06_refresh_tokens`)
- **OAuth 2.0 with GitHub** as a second way to log in (:ref:`ch06_oauth2`)
- **SSO with OpenID Connect**, mostly as concepts, with an optional Keycloak lab
  (:ref:`ch06_sso`)

:ref:`ch06_security_best_practices` covers what has to surround any of them in
production (CORS, rate limiting, secret handling), and :ref:`ch06_testing_auth` shows
how to keep a test suite fast once every write endpoint needs a token.

-----

What Changes in the BookShelf API
----------------------------------

.. list-table::
   :header-rows: 1
   :widths: 34 22 44

   * - Endpoint
     - Who may call it
     - Notes
   * - ``GET /books/…``, ``GET …/reviews``, ``GET /health``
     - Anyone
     - A public catalog stays public
   * - ``POST /books/``, ``PUT /books/{id}``
     - Any logged-in user
     - 401 without a valid token
   * - ``POST /books/{id}/reviews``
     - Any logged-in user
     - ``reviewer`` comes from the token, not from the request body
   * - ``DELETE /books/{id}``
     - Users with the ``admin`` role
     - 403 for everyone else
   * - ``POST /auth/register``, ``/auth/login``, ``/auth/refresh``, ``/auth/logout``
     - Anyone
     - Login is rate-limited
   * - ``GET /auth/github``, ``/auth/github/callback``
     - Anyone
     - The OAuth 2.0 flow
   * - ``GET /auth/me``
     - Any logged-in user
     - Shows who the token belongs to

There is no frontend. You will drive every flow with ``curl``, the Swagger UI at
``/docs``, and, for the OAuth redirect, a browser.

.. warning::

   Everything in this chapter assumes the traffic is encrypted. A bearer token sent over
   plain HTTP is a password sent over plain HTTP: anyone on the path can copy it and use
   it. The labs use ``http://localhost``, which never leaves your machine. Chapter 7 puts
   Nginx with TLS in front of the API, and only then is it fit to be reachable from a
   network.
