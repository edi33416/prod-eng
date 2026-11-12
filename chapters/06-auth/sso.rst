.. _ch06_sso:

Single Sign-On (SSO)
=====================

One Key to Many Mailboxes
--------------------------

In June 2023, the US State Department noticed unusual access to its Microsoft-hosted
email. Microsoft's investigation found that a threat actor it calls **Storm-0558** had
obtained a Microsoft **consumer** account signing key, the private key used to sign
tokens for personal Outlook.com accounts, and used it to forge tokens that opened the
**enterprise** mailboxes of about 25 organizations, US government agencies among them.

Two failures combined. The key should never have been reachable, and the US Cyber Safety
Review Board's 2024 report spends many pages on how it was. But a key for consumer
accounts should also never have been **accepted** for enterprise mail. A validation flaw
let services trust a token as long as the signature checked out against *some* Microsoft
key, without checking that the key and the issuer belonged to the right tenant type.

In an SSO system, every application trusts tokens signed by a central **Identity
Provider** (IdP). That centralization is the point of SSO, and it is also its main risk.
Each application must verify **who signed** the token, **who issued** it, and **who it
is for**, every time.

-----

What SSO Is
------------

Without SSO, every application has its own users table, its own login page, and its own
password for each person. An employee who leaves must be removed from twenty systems.
Someone always forgets the twenty-first.

With SSO, one **Identity Provider** holds the accounts. Applications (called **Relying
Parties** or **clients**) send users there to log in and accept what it says.

.. code-block:: text

   Browser          App A (BookShelf)        IdP (Keycloak)         App B (Admin UI)
     │ 1. visit App A    │                        │                        │
     │──────────────────▶│ not logged in          │                        │
     │ 2. redirect to IdP│                        │                        │
     │◀──────────────────│                        │                        │
     │ 3. login form, username + password         │                        │
     │───────────────────────────────────────────▶│ creates an IdP SESSION │
     │ 4. redirect back with code                 │ (cookie on the IdP's   │
     │◀───────────────────────────────────────────│  domain)               │
     │ 5. code ─────────▶│ exchange code ────────▶│                        │
     │                   │◀──── ID token ─────────│                        │
     │   logged in to A  │                        │                        │
     │                                                                     │
     │ 6. visit App B ────────────────────────────────────────────────────▶│
     │ 7. redirect to IdP ◀────────────────────────────────────────────────│
     │ 8. GET authorize (IdP session cookie sent) │                        │
     │───────────────────────────────────────────▶│ session exists:        │
     │ 9. redirect back with code, NO login form  │ no password asked      │
     │◀───────────────────────────────────────────│                        │
     │ 10. code ──────────────────────────────────────────────────────────▶│
     │                                            │◀── exchange code ──────│
     │   logged in to B                           │──── ID token ─────────▶│

The **session state lives at the IdP**. Each application has its own local session or
tokens, but a user is "logged in to the company" only in the IdP's records. Disable the
account there, and nobody can obtain new tokens for any application.

-----

OpenID Connect: OAuth 2.0 Plus Identity
----------------------------------------

The GitHub flow in :ref:`ch06_oauth2` had an awkward last step. OAuth gave us an
**access token for GitHub's API**, and we had to **call that API** (``/user``) to find
out who logged in. OAuth 2.0 was designed for delegated access, not for identity, and
every provider exposed identity differently.

**OpenID Connect (OIDC)** standardizes the identity part on top of OAuth 2.0:

- The client adds the scope ``openid`` (plus ``profile``, ``email`` as needed).
- The token response contains an **ID token**: a JWT, signed by the IdP, that states
  who the user is.
- Every IdP publishes a **discovery document** at
  ``<issuer>/.well-known/openid-configuration`` listing its endpoints and keys, so
  clients configure themselves from a single URL.

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * -
     - ID token
     - Access token
   * - Answers
     - "Who logged in, when, and how?"
     - "What may the bearer do at an API?"
   * - Audience (``aud``)
     - The **client** (your app)
     - The **API** (resource server)
   * - Your app should
     - Verify it, read the claims, then create its own session/tokens
     - Forward it to the API; never parse it to learn who the user is
   * - Format
     - Always a JWT
     - Anything; often a JWT, sometimes opaque

An application that receives an ID token must verify, in this order:

#. the **signature**, with the IdP's public key from its JWKS URL, choosing the key by
   the token's ``kid`` header and the algorithm from **your** allow-list (``RS256``)
#. ``iss`` equals the issuer you configured, character for character
#. ``aud`` contains **your** client ID: a token minted for App B must not log anyone in
   to App A
#. ``exp`` is in the future
#. ``nonce`` equals the value you sent in the authorization request, which prevents
   replaying an old ID token

Storm-0558 got through a gap at the equivalent of steps 1–2.

.. admonition:: Crash Course: OIDC vs SAML
   :class: dropdown

   **SAML 2.0** (2005) is the older SSO standard. The IdP sends the browser an XML
   document (an *assertion*), signed with XML Signature, which the browser POSTs to the
   application. It is everywhere in enterprise software: Salesforce, Workday, AWS
   console federation, most "SSO" checkboxes in B2B SaaS pricing tables.

   **OIDC** (2014) carries the same information as a JSON Web Token over the OAuth 2.0
   flows you already know.

   .. list-table::
      :header-rows: 1

      * -
        - SAML 2.0
        - OpenID Connect
      * - Token format
        - XML assertion, XML Signature
        - JWT (JSON), JWS
      * - Transport
        - Browser POST / redirect bindings
        - OAuth 2.0 redirects + back-channel token call
      * - Clients
        - Browser-based web apps
        - Web, SPA, mobile, CLI, service-to-service
      * - Discovery
        - XML metadata file
        - ``/.well-known/openid-configuration``
      * - Typical pain
        - XML canonicalization and signature-wrapping bugs
        - Skipping ``aud``/``iss``/``nonce`` checks

   Choose OIDC for anything new. Expect SAML when a large customer says "we need SSO
   with our IdP": most IdPs (Entra ID, Okta, Keycloak) speak both, and a library such as
   ``python3-saml`` or a proxy handles the XML.

   For a deeper dive: `OpenID Connect Core 1.0
   <https://openid.net/specs/openid-connect-core-1_0.html>`_

-----

SSO Providers and When to Use SSO
----------------------------------

**Self-hosted:** Keycloak (CNCF incubating project; the lab below), Authentik, ZITADEL,
Dex (a thin OIDC layer in front of other IdPs). **Hosted:** Microsoft Entra ID, Okta,
Auth0, Google Workspace, AWS IAM Identity Center.

Use SSO when several applications share **the same people**: a company's internal
tools, a product suite, the dashboards of Chapters 8 and 9 (Grafana speaks OIDC). Do
not build your own IdP. For a public consumer API like BookShelf, "Log in with GitHub /
Google" (:ref:`ch06_oauth2`) is effectively SSO with somebody else's IdP. If the
BookShelf team later adds an admin UI and a Grafana instance, that is when a Keycloak
realm starts to pay off.

.. warning::

   The IdP becomes the most critical service you run. If it is down, nobody logs in to
   anything. If it is compromised, the attacker is everyone. Run it highly available,
   patch it first, monitor it most closely, and protect its admin accounts with
   hardware-backed MFA.

-----

Lab (Optional): Keycloak
-------------------------

``support/keycloak/`` starts Keycloak in development mode and imports a realm:

.. code-block:: yaml

   services:
     keycloak:
       image: quay.io/keycloak/keycloak:26.8.2
       command: ["start-dev", "--import-realm"]
       environment:
         # Keycloak 26 replaced KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD with these.
         KC_BOOTSTRAP_ADMIN_USERNAME: admin
         KC_BOOTSTRAP_ADMIN_PASSWORD: admin
         KC_HEALTH_ENABLED: "true"
       ports:
         - "127.0.0.1:8080:8080"
       volumes:
         # Every *.json here is imported at startup if the realm does not exist.
         - ./import:/opt/keycloak/data/import:ro

Older tutorials use ``image: quay.io/keycloak/keycloak:latest`` with
``KEYCLOAK_ADMIN``. The variables were renamed in Keycloak 26, and ``latest`` means your
lab breaks the day a new major version ships. Pin the version, as in Chapter 4.

``import/realm-bookshelf.json`` defines a realm ``bookshelf`` with:

- two confidential clients, ``bookshelf-api`` (redirect URI
  ``http://localhost:8000/auth/oidc/callback``) and ``bookshelf-admin-ui``
  (``http://localhost:9000/callback``), both requiring PKCE
- a realm role ``bookshelf-admin``
- users ``alice`` (password ``alice-password-123``, has ``bookshelf-admin``) and ``bob``
  (``bob-password-1234``)

.. code-block:: bash

   $ cd support/keycloak
   $ docker compose up -d
   $ docker compose logs keycloak | grep -E "imported|started in"
   ... INFO  [org.keycloak.exportimport.util.ImportUtils] (main) Realm 'bookshelf' imported
   ... INFO  [io.quarkus] (main) Keycloak 26.8.2 on JVM (powered by Quarkus 3.40.1.1) started in 17.606s. Listening on: http://0.0.0.0:8080. Management interface listening on http://0.0.0.0:9000.

The discovery document is the only URL a client needs:

.. code-block:: bash

   $ curl -s localhost:8080/realms/bookshelf/.well-known/openid-configuration \
       | jq '{issuer, authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri}'
   {
     "issuer": "http://localhost:8080/realms/bookshelf",
     "authorization_endpoint": "http://localhost:8080/realms/bookshelf/protocol/openid-connect/auth",
     "token_endpoint": "http://localhost:8080/realms/bookshelf/protocol/openid-connect/token",
     "userinfo_endpoint": "http://localhost:8080/realms/bookshelf/protocol/openid-connect/userinfo",
     "jwks_uri": "http://localhost:8080/realms/bookshelf/protocol/openid-connect/certs"
   }

   $ curl -s localhost:8080/realms/bookshelf/protocol/openid-connect/certs \
       | jq '.keys[] | select(.use=="sig") | {kid, kty, alg, use, n: (.n[:24]+"..."), e}'
   {
     "kid": "Q-Dy48R96S2jVkghmsSeahHzirJNmHc4rP-Ac38R4C8",
     "kty": "RSA",
     "alg": "RS256",
     "use": "sig",
     "n": "lfRPv4wfrvoOkEMdfY7BW2t3...",
     "e": "AQAB"
   }

The JWKS holds the IdP's **public** keys. Anyone may fetch them, and with them anyone can
verify the IdP's tokens but nobody can sign one. That is the asymmetric case from the
signing crash course in :ref:`ch06_jwt_fundamentals`.

Watching SSO Happen
"""""""""""""""""""

Log in to the admin console at http://localhost:8080 (``admin`` / ``admin``) and look
around the ``bookshelf`` realm: **Clients**, **Users**, **Realm roles**, and
**Sessions**.

To see every request of the flow, ``support/keycloak/sso_demo.py`` plays the browser. It
keeps cookies, submits the login form, and logs in to **both** clients one after the
other with the same cookie jar:

.. code-block:: bash

   $ pip install httpx "pyjwt[crypto]"
   $ python sso_demo.py

   === bookshelf-api ===
   [browser] IdP shows a login form -> submitting credentials
   [browser] redirected to http://localhost:8000/auth/oidc/callback?code=fb25119c-d16...
   [backend] token response keys: ['access_token', 'expires_in', 'id_token', 'not-before-policy', 'refresh_expires_in', 'refresh_token', 'scope', 'session_state', 'token_type']
   [backend] ID token verified with key id Q-Dy48R96S2jVkghmsSeahHzirJNmHc4rP-Ac38R4C8
             iss    = http://localhost:8080/realms/bookshelf
             aud    = bookshelf-api
             sub    = 9b82c905-8bf8-4a1c-9bbb-d14be7a1e6ba
             email  = alice@example.com
             sid    = Jc94zwr1cjQ3dzqJWdyQ_aOF

   === bookshelf-admin-ui ===
   [browser] IdP already has a session -> no login form
   [browser] redirected to http://localhost:9000/callback?code=3a64d6f2-1ba...
   [backend] token response keys: ['access_token', 'expires_in', 'id_token', 'not-before-policy', 'refresh_expires_in', 'refresh_token', 'scope', 'session_state', 'token_type']
   [backend] ID token verified with key id Q-Dy48R96S2jVkghmsSeahHzirJNmHc4rP-Ac38R4C8
             iss    = http://localhost:8080/realms/bookshelf
             aud    = bookshelf-admin-ui
             sub    = 9b82c905-8bf8-4a1c-9bbb-d14be7a1e6ba
             email  = alice@example.com
             sid    = Jc94zwr1cjQ3dzqJWdyQ_aOF

That is SSO in two blocks of output. The second client got a code **without a login
form**, because the browser presented Keycloak's session cookie. Both ID tokens carry the
same ``sub`` (the user) and the same ``sid`` (the IdP session), and different ``aud``
values. Neither application ever saw Alice's password.

A complete ID token payload:

.. code-block:: json

   {
     "exp": 1794485825,
     "iat": 1794485525,
     "auth_time": 1794485525,
     "jti": "ccf6c976-8831-c7f6-1ccf-45596c73ed47",
     "iss": "http://localhost:8080/realms/bookshelf",
     "aud": "bookshelf-api",
     "sub": "9b82c905-8bf8-4a1c-9bbb-d14be7a1e6ba",
     "typ": "ID",
     "azp": "bookshelf-api",
     "nonce": "pJtNsRT83FnsRy0e9aPitA",
     "sid": "MuXCHHOT88IfZMAowlxTYZP1",
     "at_hash": "Uu0LdiPZSSgxkbhP9pq0Jw",
     "acr": "1",
     "email_verified": true,
     "name": "Alice Liddell",
     "preferred_username": "alice",
     "given_name": "Alice",
     "family_name": "Liddell",
     "email": "alice@example.com"
   }

The ``bookshelf-admin`` role is **not** in the ID token. By default Keycloak puts realm
roles in the **access token** (claim ``realm_access.roles``), because roles are about
access, not identity. To use them for the BookShelf ``admin`` role, either read them
from the access token or add a mapper that copies them into the ID token (exercise 3).

The verification code in ``sso_demo.py`` is the checklist from above, in five lines:

.. code-block:: python

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

``PyJWKClient`` fetches the JWKS, picks the key by ``kid``, and caches it. When the IdP
**rotates** its keys, it publishes the new one first, and clients that look keys up by
``kid`` keep working without a deploy.

.. code-block:: bash

   $ docker compose down       # in support/keycloak

-----

**Exercises**

#. **(Conceptual)** Draw a sequence diagram for SSO across two applications using OIDC,
   with lanes Browser, App A, App B, IdP. Label every arrow as *redirect*,
   *authentication*, *token issuance* or *token verification*. Mark the arrow where the
   IdP session is created and the arrow where it is reused. Then answer: which entity
   holds the session state? What happens to App A and App B when an admin disables the
   user at the IdP: immediately, and after their local tokens expire?

#. **(Optional, hands-on)** Run the Keycloak lab and ``sso_demo.py``. Then change one
   thing at a time and observe the failure:

   - pass ``audience="bookshelf-admin-ui"`` when verifying the ``bookshelf-api`` token
   - change ``ISSUER`` to ``http://127.0.0.1:8080/realms/bookshelf``. The server is the
     same, so why does verification fail?
   - remove ``code_verifier`` from the token request
   - give the second client its own ``Browser()``, which simulates a different browser
     or device. What does the second login look like now, and why?
   - after a run, open **Sessions** in the admin console. How many sessions does Alice
     have, and which clients are attached to each? Signing her out there ends the IdP
     session. Explain why that alone does not log her out of App A, and what "single
     sign-**out**" would require from both applications.

#. **(Optional, hands-on)** Add OIDC login to the BookShelf API: ``GET /auth/oidc/login``
   and ``GET /auth/oidc/callback``, following ``sso_demo.py`` (state and PKCE verifier in
   ``HttpOnly`` cookies, as in the GitHub flow). Identify the local user by the pair
   ``(iss, sub)`` in new columns, never by ``email`` or ``preferred_username``. Grant the
   BookShelf ``admin`` role when the Keycloak access token's ``realm_access.roles``
   contains ``bookshelf-admin``. Log in as ``alice`` and ``bob`` in a browser and show
   that only Alice can delete a book.
