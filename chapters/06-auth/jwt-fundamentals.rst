.. _ch06_jwt_fundamentals:

JSON Web Tokens (JWT)
======================

The Token That Signed Itself
-----------------------------

In March 2015, security researcher Tim McLean published a review of JWT libraries. Many
of them, across several languages, accepted this token as valid:

.. code-block:: text

   eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyNDIiLCJyb2xlIjoiYWRtaW4ifQ.

Decoded, the header says ``{"alg":"none"}``: "this token is not signed". The JWT
specification allows that algorithm for cases where integrity is guaranteed some other
way. The libraries read the algorithm **from the token** and obeyed it, so anyone could
write ``"role": "admin"`` into a payload, leave the signature empty, and be an admin.

A second bug in the same libraries was subtler. A server that verified tokens with an
RSA **public** key could be sent a token whose header said ``HS256``. The library then
used the public key, which is public, as an HMAC secret, so anyone could sign valid
tokens.

Both bugs have the same root cause: the server let the token decide how the token
should be checked. Keep that in mind for this page. A JWT is simple, and almost every
JWT vulnerability comes from trusting a part of it that has not been verified yet.

-----

Anatomy of a JWT
-----------------

A JWT is three base64url-encoded parts separated by dots:

.. code-block:: text

   header.payload.signature

Create one with PyJWT, the library the BookShelf API uses:

.. code-block:: python

   >>> import jwt
   >>> from datetime import UTC, datetime, timedelta
   >>> SECRET = "dev-only-secret-for-the-jwt-lab-0123456789"
   >>> now = datetime.now(UTC)
   >>> token = jwt.encode(
   ...     {"sub": "user42", "role": "user", "iat": now, "exp": now + timedelta(minutes=30)},
   ...     SECRET,
   ...     algorithm="HS256",
   ... )
   >>> token
   'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyNDIiLCJyb2xlIjoidXNlciIsImlhdCI6MTc5NDQ4NTU2NiwiZXhwIjoxNzk0NDg3MzY2fQ.87HmZwYKZKeZkO6GZ4pa19rXAxYs0Bk0qd351hDzDuc'

Split it and decode the first two parts. No key is needed:

.. code-block:: python

   >>> import base64
   >>> def b64d(part):
   ...     return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
   ...
   >>> header, payload, signature = token.split(".")
   >>> b64d(header)
   b'{"alg":"HS256","typ":"JWT"}'
   >>> b64d(payload)
   b'{"sub":"user42","role":"user","iat":1794485566,"exp":1794487366}'

**Header**
   How the token is signed (``alg``) and what it is (``typ``).

**Payload**
   The **claims**: statements about the user and about the token itself. ``iat`` and
   ``exp`` are Unix timestamps; ``exp - iat`` is 1800 seconds, the 30 minutes we asked
   for.

**Signature**
   An HMAC-SHA256 of the string ``header.payload``, computed with the secret. Nothing
   magic: you can compute it yourself and get the same bytes PyJWT produced:

   .. code-block:: python

      >>> import hashlib, hmac
      >>> mac = hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256)
      >>> base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode()
      '87HmZwYKZKeZkO6GZ4pa19rXAxYs0Bk0qd351hDzDuc'
      >>> signature
      '87HmZwYKZKeZkO6GZ4pa19rXAxYs0Bk0qd351hDzDuc'

.. warning::

   **A JWT is signed, not encrypted.** Anyone who has the token can read every claim,
   as you just did without the key. Never put a password, an API key, an email address
   you would not print on a postcard, or anything else confidential in a JWT payload.
   The signature only guarantees that nobody **changed** the claims.

-----

Verifying a Token
------------------

``jwt.decode`` checks the signature and the expiry, then returns the claims:

.. code-block:: python

   >>> jwt.decode(token, SECRET, algorithms=["HS256"])
   {'sub': 'user42', 'role': 'user', 'iat': 1794485566, 'exp': 1794487366}

Change one claim, keep the old signature, and verification fails:

.. code-block:: python

   >>> forged = base64.urlsafe_b64encode(
   ...     b64d(payload).replace(b'"user"', b'"admin"')
   ... ).rstrip(b"=").decode()
   >>> jwt.decode(f"{header}.{forged}.{signature}", SECRET, algorithms=["HS256"])
   Traceback (most recent call last):
     ...
   jwt.exceptions.InvalidSignatureError: Signature verification failed

To produce a valid signature for the forged payload, the attacker needs ``SECRET``. That
is the entire security of an HS256 token, so the secret has to be long, random and kept
out of the code (:ref:`ch06_implementing_jwt`).

The ``alg: none`` token from the opening is rejected, because ``algorithms=["HS256"]`` is
an allow-list chosen by the server, not by the token:

.. code-block:: python

   >>> none_token = jwt.encode({"sub": "user42", "role": "admin"}, None, algorithm="none")
   >>> jwt.decode(none_token, SECRET, algorithms=["HS256"])
   Traceback (most recent call last):
     ...
   jwt.exceptions.InvalidAlgorithmError: The specified alg value is not allowed

PyJWT makes ``algorithms`` a required argument for exactly this reason. Libraries
learned this the hard way in 2015.

.. code-block:: python

   >>> jwt.decode(token, options={"verify_signature": False})
   {'sub': 'user42', 'role': 'user', 'iat': 1794485566, 'exp': 1794487366}

That last call is for **debugging only**: it reads the claims without checking anything.
Never use the result of an unverified decode to make a decision.

-----

Standard Claims
----------------

RFC 7519 registers a few claim names. Use them instead of inventing your own:

.. list-table::
   :header-rows: 1
   :widths: 10 22 68

   * - Claim
     - Meaning
     - What the BookShelf API puts there
   * - ``sub``
     - Subject
     - The user's database ID, as a string: ``"1"``. Never the username, which can
       change.
   * - ``exp``
     - Expiration time
     - Now + 15 minutes. ``jwt.decode`` rejects the token after this.
   * - ``iat``
     - Issued at
     - Now. Useful for debugging and for "log out everywhere before time T".
   * - ``iss``
     - Issuer
     - ``"bookshelf"``: who created the token.
   * - ``aud``
     - Audience
     - ``"bookshelf-api"``: who the token is **for**. A token minted for another service
       that happens to share the key is rejected.
   * - ``jti``
     - JWT ID
     - Not used. A unique ID per token, needed only if you keep a deny-list.

Anything else is a private claim. We add ``username`` and ``role``. Both are copies of
database values, frozen at the moment the token was issued. :ref:`ch06_refresh_tokens`
deals with what happens when the database changes.

-----

Token Lifecycle
----------------

.. code-block:: text

   Client                                         BookShelf API
     │  POST /auth/login {username, password}          │
     │ ───────────────────────────────────────────────▶│ verify password hash
     │  {"access_token": "eyJ...", ...}                │ sign claims with secret
     │ ◀───────────────────────────────────────────────│
     │                                                 │
     │  POST /books/                                   │
     │  Authorization: Bearer eyJ...                   │
     │ ───────────────────────────────────────────────▶│ verify signature + exp
     │  201 Created                                    │ (no database lookup)
     │ ◀───────────────────────────────────────────────│

The server keeps **no session state**. Any replica of the API with the secret can verify
any token. Chapter 4's Compose stack can run three ``api`` containers behind a load
balancer without a shared session store.

The price is **revocation**. A signed token is valid until ``exp``, and the server has
no list of tokens it could delete one from. That is why production systems use two
kinds of token:

**Access token**
   A JWT. Short-lived (5–60 minutes, 15 in the BookShelf API). Sent with every request.
   If it leaks, it is useful for minutes.

**Refresh token**
   Long-lived (days or weeks). Sent to exactly one endpoint, ``/auth/refresh``, to get a
   new access token. Stored server-side, so it **can** be revoked. The BookShelf API
   uses an opaque random string rather than a JWT for it (:ref:`ch06_refresh_tokens`).

.. admonition:: Crash Course: Cryptographic Signing
   :class: dropdown

   A **signature** lets a verifier check that a message came from the holder of a key
   and was not modified. It does **not** hide the message: that would be
   **encryption**, a different operation with different keys.

   **HMAC (HS256): symmetric.** One shared secret both signs and verifies. HMAC-SHA256
   mixes the secret into a SHA-256 hash of the message. Without the secret you cannot
   compute a valid tag, and you cannot recover the secret from tags.

   .. code-block:: text

      signature = HMAC-SHA256(secret, header + "." + payload)
      verify:     recompute and compare (in constant time)

   **RSA / ECDSA (RS256, ES256): asymmetric.** A **private** key signs and a
   **public** key verifies. The public key can be published, and identity providers
   do exactly that at a JWKS URL (you will fetch one in :ref:`ch06_sso`).

   .. list-table::
      :header-rows: 1

      * -
        - HS256
        - RS256 / ES256
      * - Who can verify
        - Anyone with the secret, who can then also **sign**
        - Anyone with the public key, who **cannot** sign
      * - Good for
        - One service that issues and checks its own tokens
        - An issuer (IdP) and many verifying services
      * - Key size
        - ≥ 32 random bytes
        - RSA ≥ 2048 bits, or P-256 for ES256

   The BookShelf API issues and verifies its own tokens, so HS256 is the right fit.
   If a second service had to verify BookShelf tokens, giving it the HMAC secret would
   also let it **mint** BookShelf tokens. At that point you switch to RS256 or ES256
   and give it only the public key.

   For a deeper dive: `RFC 7515 — JSON Web Signature <https://www.rfc-editor.org/rfc/rfc7515>`_

-----

**Exercises**

#. Paste the token from `Anatomy of a JWT`_ into the debugger at `jwt.io
   <https://jwt.io>`_. Identify header, payload and signature, and confirm the payload
   decodes without a key. Then do the same offline with the ``b64d`` helper above.
   PyJWT has no command-line tool, so Python is the offline way. Which of the two would
   you use for a **production** token, and why?

#. In the debugger, change one character of the payload. What does jwt.io report about
   the signature? Paste the secret ``dev-only-secret-for-the-jwt-lab-0123456789`` into
   the verify box and watch the signature become valid again. What does that tell you
   about pasting real secrets into a website?

#. In a Python shell inside the starter's virtual environment, create a token with the
   claims ``{"sub": "user42", "role": "user"}`` and an ``exp`` 30 minutes from now,
   signed with a secret of your choice. Decode and verify it. Then:

   - decode it with a different secret, and note the exception
   - decode it with ``algorithms=["HS512"]``, and note the exception
   - create a token whose ``exp`` is 5 seconds away, wait 6 seconds, decode it, and
     confirm you get ``ExpiredSignatureError: Signature has expired``

#. Sign a token with the secret ``"short"``. PyJWT does not refuse. Read the warning it
   prints. Why is a short HMAC secret a problem when an attacker has a single valid
   token? (Hint: what can the attacker compute offline, and how fast?)
