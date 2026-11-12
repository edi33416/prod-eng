.. _ch06_security_best_practices:

Auth Security Best Practices
=============================

Fourteen Thousand Logins, Seven Million Victims
------------------------------------------------

In October 2023, the genetic testing company 23andMe disclosed that attackers had logged
in to about **14,000** customer accounts. They did not hack 23andMe's servers. They used
**credential stuffing**: taking email/password pairs leaked from *other* sites' breaches
and trying them on 23andMe, betting that people reuse passwords. Enough did.

Through the "DNA Relatives" feature, each compromised account could see data about
hundreds of genetic relatives. The 14,000 logins exposed information about roughly
**6.9 million** people. The company later settled a class action for $30 million and
filed for bankruptcy in 2025.

The login endpoint behaved exactly as written: correct password, access granted. What
was missing was everything **around** it: limits on how many logins one source may try,
detection of a wave of logins from new locations, and a second factor. This page covers
the surrounding measures that apply to the BookShelf API.

-----

Passwords
----------

- **Hash with a slow, salted, memory-hard function**: Argon2id (our choice), scrypt or
  bcrypt. Never MD5, SHA-1 or SHA-256, even "with a salt". The crash course below
  explains why.
- **Never store, log or echo plaintext.** That includes 422 error bodies
  (:ref:`ch06_implementing_jwt`), debug logs of request bodies, and exception
  tracebacks. ``SecretStr`` helps with the last two.
- **Length over complexity.** NIST SP 800-63B: allow long passwords (we allow 128
  characters), do not force character classes or periodic changes, and do check new
  passwords against lists of breached passwords (exercise 3).
- **Same response for unknown user and wrong password**, in content **and** timing.

.. admonition:: Crash Course: Password Hashing
   :class: dropdown

   A password hash must stay safe **after the database leaks**, because eventually one
   does. The attacker then has unlimited offline guesses, and the only defence is
   making each guess expensive.

   **Why SHA-256 is wrong.** It was designed to be *fast*. One laptop computes about a
   million SHA-256 hashes per second (measured on the machine that built this chapter:
   ``sha256 x1e6: 698 ms``). A GPU rig does billions. A leaked table of SHA-256 password
   hashes falls to a dictionary attack in hours. In 2012, 6.5 million LinkedIn password
   hashes appeared on a forum: unsalted SHA-1. Most were cracked within days. The full
   dump, published in 2016, held 117 million.

   **Salt.** A random value per password, stored next to the hash and mixed in before
   hashing. Without salt, identical passwords give identical hashes, and one
   precomputed table (a "rainbow table") cracks every user at once. With salt, every
   hash must be attacked separately. A salt is **not** secret.

   **Work factor.** Password hashes have a tunable cost. bcrypt has ``cost`` (2^cost
   rounds). Argon2 has time (passes), **memory** and parallelism. Memory-hardness is
   Argon2's advantage: 64 MiB per guess makes GPU and ASIC attacks far more expensive,
   because those chips have lots of compute but little memory per core.

   .. code-block:: text

      $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
                    64 MiB ─┘   │   └─ 4 lanes
                       3 passes ┘

   Pick parameters so one verification takes roughly 50–500 ms on your servers (ours:
   66 ms), and raise them as hardware gets faster. ``pwdlib`` can tell you when a
   stored hash uses outdated parameters (``verify_and_update``), so you can re-hash at
   the next successful login.

   bcrypt has one more trap: it ignores everything after **72 bytes** of input, so long
   passphrases silently lose their tail. Current ``bcrypt`` raises an error instead,
   which is what crashed passlib in :ref:`ch06_implementing_jwt`.

   For a deeper dive: `OWASP Password Storage Cheat Sheet
   <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>`_

-----

Tokens
-------

.. list-table::
   :header-rows: 1
   :widths: 44 56

   * - Practice
     - In the BookShelf API
   * - Short-lived access tokens
     - 15 minutes (``ACCESS_TOKEN_EXPIRE_MINUTES``)
   * - Revocable refresh tokens, stored server-side, hashed
     - ``refresh_tokens`` table, SHA-256, rotation + reuse detection
   * - Fixed algorithm allow-list, required claims, ``iss``/``aud`` checked
     - ``decode_access_token``
   * - Long random signing secret, from the environment, fail fast if missing
     - ``JWT_SECRET_KEY``, ≥ 32 characters, checked at start-up
   * - Nothing sensitive in the payload
     - ``sub``, ``username``, ``role``, standard claims. No email, no password hash.
   * - Cookies: ``HttpOnly``, ``Secure``, ``SameSite``, narrow ``Path``
     - OAuth state cookie: all four. ``COOKIE_SECURE`` defaults to ``true``.
   * - Tokens never in URLs
     - Bearer header and JSON bodies only

**HTTPS only.** A bearer token is a password with an expiry date. Over plain HTTP,
anyone on the network path (the coffee shop Wi-Fi, a compromised router, a corporate
proxy) can copy it. Chapter 7 terminates TLS at Nginx with a Let's Encrypt certificate
and redirects all HTTP to HTTPS. Until then, the API must only be reachable on
``localhost``.

**CSRF.** A malicious page can make the victim's browser **send** requests to your API,
and the browser automatically attaches cookies for your domain. An API that
authenticates with a **cookie** is therefore exposed to cross-site request forgery. An
API that authenticates with an ``Authorization: Bearer`` header is not, because the
browser never adds that header on its own. The BookShelf API's only cookie is the OAuth
state cookie, which protects against exactly this (:ref:`ch06_oauth2`). If you move the
refresh token into a cookie, ``SameSite=Strict`` and ``Path=/auth/refresh`` keep it
from being sent on cross-site requests.

-----

CORS
-----

Browsers enforce the **same-origin policy**: JavaScript on ``https://evil.example`` may
send a request to ``https://api.bookshelf.example.com``, but may not **read the
response** unless the API explicitly allows that origin. **Cross-Origin Resource
Sharing** is how the API grants the permission, with ``Access-Control-Allow-*``
response headers.

For requests with an ``Authorization`` header or a JSON body, the browser first sends
a **preflight** ``OPTIONS`` request asking whether the real request is allowed.

Configuration in ``main.py``:

.. code-block:: python

   # Browsers only let pages from these origins call the API from JavaScript.
   # Comma-separated, e.g. "https://bookshelf.example.com,http://localhost:3000".
   _allowed_origins = [
       origin.strip()
       for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
       if origin.strip()
   ]
   app.add_middleware(
       CORSMiddleware,
       allow_origins=_allowed_origins,
       allow_methods=["GET", "POST", "PUT", "DELETE"],
       allow_headers=["Authorization", "Content-Type"],
       # Tokens travel in the Authorization header, not in cookies.
       allow_credentials=False,
   )

With ``CORS_ALLOWED_ORIGINS=https://bookshelf.example.com``, a preflight from the
allowed origin:

.. code-block:: bash

   $ curl -si -X OPTIONS localhost:8000/books/ \
       -H 'Origin: https://bookshelf.example.com' \
       -H 'Access-Control-Request-Method: POST' \
       -H 'Access-Control-Request-Headers: authorization, content-type'
   HTTP/1.1 200 OK
   date: Thu, 12 Nov 2026 12:09:39 GMT
   server: uvicorn
   vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers, Access-Control-Request-Private-Network
   access-control-allow-methods: GET, POST, PUT, DELETE
   access-control-max-age: 600
   access-control-allow-headers: Accept, Accept-Language, Authorization, Content-Language, Content-Type
   access-control-allow-origin: https://bookshelf.example.com
   content-length: 2
   content-type: text/plain; charset=utf-8

   OK

and from any other origin:

.. code-block:: bash

   $ curl -si -X OPTIONS localhost:8000/books/ \
       -H 'Origin: https://evil.example' \
       -H 'Access-Control-Request-Method: POST'
   HTTP/1.1 400 Bad Request
   ...
   content-type: text/plain; charset=utf-8

   Disallowed CORS origin

A simple ``GET`` from a foreign origin still gets its data, just without the
``Access-Control-Allow-Origin`` header:

.. code-block:: bash

   $ curl -si localhost:8000/books/ -H 'Origin: https://evil.example' | head -6
   HTTP/1.1 200 OK
   date: Thu, 12 Nov 2026 12:09:39 GMT
   server: uvicorn
   content-length: 91
   content-type: application/json
   vary: Origin

.. admonition:: Observation:

   CORS is **not** access control. ``curl``, Python, and any server ignore it
   completely. The server answered the ``evil.example`` GET with the full book list.
   CORS only stops a **browser** from handing the response to a **page** from another
   origin, which protects users' browsers from being used against your API. Endpoints
   still need authentication. And never "fix" a CORS error with
   ``allow_origins=["*"]`` together with ``allow_credentials=True``: Starlette then
   reflects any origin back, and every website can make credentialed calls as your
   logged-in users.

-----

Rate Limiting the Login
------------------------

The login endpoint verifies a password, so every attempt is a guess. Without a limit, a
script can try thousands of passwords per minute per account, or one common password
against every account (*password spraying*). The BookShelf API allows **5 login
attempts per minute per client IP**:

.. code-block:: python

   class RateLimiter:
       """Sliding-window limit of `times` requests per `seconds`, per client IP.

       State lives in this process's memory. With several workers or replicas,
       each one counts separately; move the counters to Redis or enforce the
       limit at the reverse proxy (Chapter 7).
       """

       def __init__(self, times: int, seconds: float) -> None:
           self.times = times
           self.seconds = seconds
           self._hits: dict[str, deque[float]] = defaultdict(deque)
           self._lock = threading.Lock()

       def __call__(self, request: Request) -> None:
           key = request.client.host if request.client else "unknown"
           now = time.monotonic()
           with self._lock:
               hits = self._hits[key]
               while hits and hits[0] <= now - self.seconds:
                   hits.popleft()
               if len(hits) >= self.times:
                   retry_after = math.ceil(hits[0] + self.seconds - now)
                   raise HTTPException(
                       status_code=429,
                       detail="Too many requests",
                       headers={"Retry-After": str(retry_after)},
                   )
               hits.append(now)


   login_rate_limit = RateLimiter(times=5, seconds=60)

An instance with ``__call__`` is a valid FastAPI dependency:
``dependencies=[Depends(login_rate_limit)]`` on ``/auth/login``. The lock is needed
because FastAPI runs synchronous dependencies in a thread pool. ``time.monotonic()``
does not jump when the system clock is adjusted.

.. code-block:: bash

   $ for i in $(seq 1 8); do
       curl -s -o /dev/null -w "attempt $i: %{http_code}\n" -X POST localhost:8000/auth/login \
         -H 'Content-Type: application/json' -d '{"username":"alice","password":"guess'$i'"}'
     done
   attempt 1: 401
   attempt 2: 401
   attempt 3: 401
   attempt 4: 401
   attempt 5: 401
   attempt 6: 429
   attempt 7: 429
   attempt 8: 429

   $ curl -si -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
       -d '{"username":"alice","password":"x"}' | grep -iE "^HTTP|retry-after|detail"
   HTTP/1.1 429 Too Many Requests
   retry-after: 60
   {"detail":"Too many requests"}

Know the limitations of this implementation:

- **Successful logins count too.** The limit is on attempts, not failures.
- **State is per process.** ``uvicorn --workers 4`` or three API replicas give an
  attacker four or three times the budget, and a restart resets the counters. The
  production version stores counters in Redis (already in the Compose stack) or, more
  commonly, enforces the limit at the reverse proxy: Nginx's ``limit_req`` in Chapter
  7.
- **The key is the client IP**, which is wrong in two directions. Behind Nginx (Chapter
  7), ``request.client.host`` is the proxy's address, and everyone shares one budget
  until Uvicorn is told to trust ``X-Forwarded-For`` from the proxy. Credential
  stuffing from a botnet spreads over thousands of IPs, each staying under the limit. A
  second limit per **username** catches spraying against one account (exercise 2), at
  the cost of letting an attacker lock a known user out.

Rate limiting is one layer. Against 23andMe-style attacks the strongest measures are
breached-password checks and a second factor (TOTP or passkeys), which are beyond this
chapter.

-----

Secrets Management
-------------------

The BookShelf API now has four secrets: ``POSTGRES_PASSWORD``, ``JWT_SECRET_KEY``,
``GITHUB_CLIENT_SECRET``, and (in the Keycloak lab) a client secret. The rules from
:ref:`ch05_secrets_environments` apply to all of them:

- they come from the environment (``.env`` locally, the platform's secret store in
  production), never from code, images, or committed files
- the app refuses to start without the ones it requires, and runs with a feature
  disabled (503) when an optional one is missing
- each environment has its own values, and staging tokens are useless in production
- **rotation** is planned in advance. Rotating ``JWT_SECRET_KEY`` invalidates every
  access token at once, which with 15-minute tokens means everyone silently refreshes.
  Supporting two keys at once (sign with the new, verify with both, identified by a
  ``kid`` header) makes rotation seamless. The JWKS in :ref:`ch06_sso` is that
  mechanism at an IdP.

-----

**Exercises**

#. Implement CORS in ``main.py`` with ``CORS_ALLOWED_ORIGINS`` and the restrictive
   method and header lists shown above. With ``curl``, send a preflight from an allowed
   origin, from a disallowed origin, and one asking for ``Access-Control-Request-Method:
   PATCH``. Explain each response. Then write the three tests in
   ``tests/integration/test_cors.py``. Note that ``tests/conftest.py`` must set the
   environment variable **before** the app is imported. Why?

#. Implement ``RateLimiter.__call__`` until ``tests/unit/test_rate_limit.py`` and the two
   rate-limit tests in ``test_auth_api.py`` pass. Send 10 rapid login requests and
   confirm that the 6th is rejected with ``429`` and a ``Retry-After`` header. Then add a
   **second** limiter keyed on the username (10 attempts per 15 minutes) and write a
   test that shows it triggering while requests come from different IPs. (Hint: the
   ``TestClient`` accepts a ``client=("10.0.0.7", 50000)`` argument.)

#. Add a breached-password check to registration using the `Have I Been Pwned range API
   <https://haveibeenpwned.com/API/v3#PwnedPasswords>`_: send only the **first five**
   hex characters of the password's SHA-1 and compare the returned suffixes locally
   (*k-anonymity*: the service never learns the password). Reject passwords seen in
   breaches with a 422. In tests, mock the HTTP call as in Chapter 3. Decide, and
   justify, what registration should do when the API is unreachable.

#. Run the API with ``uvicorn bookshelf.main:app --workers 3``. How many login attempts
   per minute does one IP really get now? Explain the result, and describe in a few
   sentences how a Redis-backed limiter would fix it (``INCR`` + ``EXPIRE`` on a key per
   IP and minute).
