.. _ch04_networking_volumes:

Networking, Volumes, and Configuration
=======================================

The stack works. This page explains *why* it works — how ``api`` finds ``db``, where
PostgreSQL keeps its data — and then makes it fit for both production and day-to-day
development: secrets out of the Compose file, and a dev mode with live reload.

-----

Container Networking
---------------------

For each project, Compose creates a **user-defined bridge network** and attaches every
service to it:

.. code-block:: bash

   $ docker network ls --filter name=bookshelf
   NETWORK ID     NAME                DRIVER    SCOPE
   eb00fe10a8f9   bookshelf_default   bridge    local

   $ docker network inspect bookshelf_default \
       --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
   bookshelf-api-1 172.24.0.4/16
   bookshelf-db-1 172.24.0.3/16
   bookshelf-cache-1 172.24.0.2/16

Each container gets its own IP on a private subnet. Docker runs an embedded DNS server
on user-defined networks that resolves **service names** to those IPs:

.. code-block:: bash

   $ docker compose exec api python -c \
       "import socket; print(socket.gethostbyname('db'), socket.gethostbyname('cache'))"
   172.24.0.3 172.24.0.2

   $ docker compose exec api python -c \
       "import socket; s=socket.create_connection(('cache', 6379), timeout=2); s.sendall(b'PING\r\n'); print(s.recv(16))"
   b'+PONG\r\n'

That is why ``DATABASE_URL`` says ``@db:5432``. Never hardcode container IPs: they are
assigned at creation and change every time the stack is recreated (the subnet above was
``172.18.0.0/16`` on the previous ``up``). Names are stable.

.. admonition:: Observation:

   The *default* ``bridge`` network that plain ``docker run`` uses does **not** have
   name-based DNS. That is the reason the manual ``docker run`` version of this stack in
   :ref:`ch04_compose` had to create its own network first.

Publishing Ports
^^^^^^^^^^^^^^^^^

Containers on the network can reach each other on *any* port. The host and the outside
world can reach a container only on ports explicitly published with ``ports:``:

.. code-block:: bash

   $ docker compose ps
   NAME                IMAGE                COMMAND                  SERVICE   STATUS                        PORTS
   bookshelf-api-1     bookshelf:latest     "uvicorn bookshelf.m…"   api       Up About a minute             0.0.0.0:8000->8000/tcp
   bookshelf-cache-1   redis:7-alpine       "docker-entrypoint.s…"   cache     Up About a minute (healthy)   6379/tcp
   bookshelf-db-1      postgres:16-alpine   "docker-entrypoint.s…"   db        Up About a minute (healthy)   5432/tcp

   $ curl -s -m 2 localhost:5432; echo "exit=$?"
   exit=7

``5432/tcp`` without an arrow means "the container listens, but nothing is published".
``curl`` exit code 7 is "failed to connect". This is exactly what you want in
production: **publish only what external clients need.** The database is an
implementation detail of the API, not a public service.

The ``ports`` syntax is ``[HOST_IP:]HOST_PORT:CONTAINER_PORT``:

- ``"8000:8000"`` — all host interfaces (``0.0.0.0``), reachable from your LAN.
- ``"127.0.0.1:5432:5432"`` — host loopback only; reachable from your own machine,
  invisible to the network. Use this for anything debug-only.

.. warning::

   Docker writes its own ``iptables`` rules for published ports, and they take
   precedence over ``ufw``. A database published as ``"5432:5432"`` on a cloud VM is
   open to the internet even if ``ufw`` says port 5432 is blocked. Internet-wide
   scanners find exposed PostgreSQL and Redis instances within hours.

-----

Volumes
--------

A container's writable layer is deleted with the container. Two mechanisms put data
somewhere else:

**Named volumes** — storage managed by Docker:

.. code-block:: yaml

   volumes:
     - pgdata:/var/lib/postgresql/data

.. code-block:: bash

   $ docker volume ls --filter name=bookshelf
   DRIVER    VOLUME NAME
   local     bookshelf_pgdata

   $ docker volume inspect bookshelf_pgdata --format '{{.Mountpoint}}'
   /var/lib/docker/volumes/bookshelf_pgdata/_data

Use them for data the *application* owns: database files, uploads. Docker creates them
with the right permissions, they work identically on every OS, and they survive
``docker compose down``.

**Bind mounts** — a host directory mapped into the container:

.. code-block:: yaml

   volumes:
     - ./src:/app/src

Use them when the *host* owns the files and the container should see changes
immediately: source code during development, a config file you edit by hand. Never
for production data — permissions and paths then depend on the host's layout.

Proving Persistence
^^^^^^^^^^^^^^^^^^^^

With two books in the database from the previous page:

.. code-block:: bash

   $ docker compose down
    Container bookshelf-api-1  Removed
    Container bookshelf-db-1  Removed
    Container bookshelf-cache-1  Removed
    Network bookshelf_default  Removed

   $ docker volume ls --filter name=bookshelf
   DRIVER    VOLUME NAME
   local     bookshelf_pgdata

   $ docker compose up -d
   $ curl -s localhost:8000/books/
   [{"id":1,"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008},{"id":2,"title":"Refactoring","author":"Martin Fowler","isbn":"9780201485677","year":1999}]

Every container was destroyed and recreated, and the data is intact. Now with ``-v``:

.. code-block:: bash

   $ docker compose down -v
    ...
    Volume bookshelf_pgdata  Removed
    Network bookshelf_default  Removed

   $ docker compose up -d
   $ curl -s localhost:8000/books/
   []

.. warning::

   ``docker compose down -v`` is the container equivalent of ``DROP DATABASE``. It is
   handy for resetting a dev environment and catastrophic on a server. A volume is also
   **not a backup** — it lives on one disk of one host. Production databases need
   ``pg_dump`` or continuous archiving to somewhere else.

-----

Configuration and Secrets
--------------------------

The Compose file from :ref:`ch04_compose` contains ``POSTGRES_PASSWORD: secret`` and the
same password again inside ``DATABASE_URL``. Committing it means every clone of the
repository — and every fork, every CI log, every laptop backup — holds the credential.

.. admonition:: Crash Course: Environment Variables in Python
   :class: dropdown

   Every process inherits a set of key-value strings from its parent: the
   **environment**. Python exposes it as ``os.environ``, a dict-like mapping:

   .. code-block:: python

      import os

      os.environ["DATABASE_URL"]            # KeyError if unset — use for required config
      os.getenv("DATABASE_URL")             # None if unset
      os.getenv("DATABASE_URL", "sqlite:///bookshelf.db")   # with a default

   Values are always strings. Convert explicitly, and be careful with booleans —
   ``bool("false")`` is ``True``:

   .. code-block:: python

      port = int(os.getenv("PORT", "8000"))
      debug = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}

   **python-dotenv** loads a ``.env`` file into ``os.environ`` for local runs outside
   Docker (it is already installed as a uvicorn dependency):

   .. code-block:: python

      from dotenv import load_dotenv
      load_dotenv()   # reads ./.env; does NOT override variables already set

   Inside containers you do not need it — Compose sets the variables directly.

   **The 12-Factor App** methodology (factor III, *Config*) states the principle behind
   all of this: configuration that varies between deploys — database URLs, credentials,
   feature flags — lives in the environment, never in code. The test: could you
   open-source the repository right now without leaking a credential?

   For a deeper dive, see: `The Twelve-Factor App — Config <https://12factor.net/config>`_

The .env File
^^^^^^^^^^^^^^

Compose automatically reads a file named ``.env`` in the project directory and uses it
for **variable interpolation** — replacing ``${VAR}`` in ``docker-compose.yml``. Commit a
template, not the real file:

.. code-block:: bash

   # .env.example — committed
   # Copy to .env and change the password. Never commit .env.
   POSTGRES_USER=bookshelf
   POSTGRES_PASSWORD=change-me
   POSTGRES_DB=bookshelf

.. code-block:: bash

   $ cp .env.example .env
   $ echo ".env" >> .gitignore
   $ $EDITOR .env          # set a real password

Now rewrite ``docker-compose.yml`` to use the variables. This is the version in
``support/docker-compose.yml``:

.. code-block:: yaml

   services:
     api:
       build: .
       image: bookshelf:latest
       ports:
         - "8000:8000"
       environment:
         DATABASE_URL: postgresql://${POSTGRES_USER:-bookshelf}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-bookshelf}
         # Provisioned now, used by later chapters (caching, LiteLLM in Ch11).
         REDIS_URL: redis://cache:6379/0
       depends_on:
         db:
           condition: service_healthy
         cache:
           condition: service_healthy
       restart: unless-stopped

     db:
       image: postgres:16-alpine
       environment:
         POSTGRES_USER: ${POSTGRES_USER:-bookshelf}
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
         POSTGRES_DB: ${POSTGRES_DB:-bookshelf}
       volumes:
         - pgdata:/var/lib/postgresql/data
       healthcheck:
         # $$ escapes Compose interpolation: the variables are expanded by the
         # shell inside the container, from the environment set above.
         test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
         interval: 5s
         timeout: 5s
         retries: 5
       restart: unless-stopped

     cache:
       image: redis:7-alpine
       healthcheck:
         test: ["CMD", "redis-cli", "ping"]
         interval: 5s
         timeout: 3s
         retries: 5
       restart: unless-stopped

   volumes:
     pgdata:

New things in this file:

- ``${VAR:-default}`` — use ``default`` if ``VAR`` is unset or empty.
- ``${VAR:?message}`` — **refuse to start** if ``VAR`` is unset or empty. A missing
  password should be a loud error, not a database with an empty password.
- ``$$VAR`` — a literal ``$`` passed to the container, so the healthcheck reads the
  container's own environment at runtime.
- ``image: bookshelf:latest`` — name the built image explicitly instead of the
  generated ``bookshelf-api``.
- ``restart: unless-stopped`` — if a process crashes (or the host reboots), Docker
  restarts it, unless you stopped it yourself.
- A ``healthcheck`` for Redis, so ``api`` can wait for ``service_healthy`` on both
  dependencies.

Try it without a ``.env``:

.. code-block:: bash

   $ mv .env .env.bak && docker compose config; mv .env.bak .env
   error while interpolating services.db.environment.POSTGRES_PASSWORD: required variable POSTGRES_PASSWORD is missing a value: Set POSTGRES_PASSWORD in .env

One file per environment
"""""""""""""""""""""""""

The same Compose file usually serves several environments: your laptop, a shared UAT
(user acceptance testing) server, production. Only the values differ, so keep one
file per environment and select it with ``--env-file``:

.. code-block:: text

   .env.example   # committed template, documents every variable
   .env.dev       # local development
   .env.uat       # UAT server: its own database name and credentials
   .env.prod      # production (often not on developer machines at all)

.. code-block:: bash

   $ docker compose --env-file .env.uat config | grep POSTGRES_DB
         POSTGRES_DB: bookshelf_uat

   $ docker compose --env-file .env.uat up -d

``--env-file`` **replaces** ``.env`` rather than adding to it. A variable that is only
in ``.env`` is not read once you pass ``--env-file``, so each environment file must be
complete.

.. admonition:: Observation:

   ``--env-file`` can be repeated. When it is, the files are merged and **the last one
   wins** for any variable defined in more than one of them:

   .. code-block:: bash

      $ docker compose --env-file .env.uat --env-file .env.local config | grep POSTGRES_
            POSTGRES_DB: bookshelf_uat            # from .env.uat
            POSTGRES_PASSWORD: override-pass      # .env.local wins

To run two environments **side by side** on one machine, give each its own project
name as well: ``docker compose -p bookshelf-uat --env-file .env.uat up -d``. Containers,
networks *and volumes* are prefixed with the project name, so UAT gets its own
``bookshelf-uat_pgdata`` instead of sharing your dev data.

Every one of these files except the template holds secrets. Ignore them all, then
re-include the template:

.. code-block:: text

   # .gitignore
   .env
   .env.*
   !.env.example

The ``.dockerignore`` from :ref:`ch04_dockerfile` already excludes ``.env.*``, so none of
them can end up in an image either.

Precedence Rules
^^^^^^^^^^^^^^^^^

When the same variable is defined in several places, the container sees the value from
the highest-priority source:

#. ``docker compose run -e VAR=…`` on the command line
#. ``environment:`` / ``env_file:`` entries whose value is interpolated from the shell or
   ``.env`` (``${VAR}``) — and for interpolation, **the shell environment beats .env**
#. ``environment:`` with a literal value in the Compose file
#. ``env_file:`` entries
#. ``ENV`` in the Dockerfile

Rule 5 is why the image's ``ENV DATABASE_URL=sqlite:////app/data/bookshelf.db`` from
:ref:`ch04_multistage` is harmless: it is a default for ``docker run``, and Compose
overrides it. Rule 2 lets you override ``.env`` for a single command:
``POSTGRES_DB=scratch docker compose up -d``.

When in doubt, ``docker compose config`` prints the fully resolved file.

.. warning::

   Environment variables are not secret *from Docker*. Anyone with access to the Docker
   daemon can read them:

   .. code-block:: bash

      $ docker compose exec api env | grep DATABASE_URL
      DATABASE_URL=postgresql://bookshelf:s3cr3t-dev-only@db:5432/bookshelf

   ``docker inspect`` shows them too. Moving secrets from the Compose file to ``.env``
   keeps them out of Git; it does not hide them on the host. Compose's ``secrets:``
   (files mounted under ``/run/secrets/``) and external secret managers go further.
   Chapter 6 revisits secrets when JWT signing keys enter the picture.

-----

Development vs Production
--------------------------

``docker-compose.yml`` now describes production: the code is baked into the image,
nothing but the API is published, containers restart on failure. That is the wrong
shape for development, where you want to edit code and see the result in a second.

Compose merges multiple files given with ``-f``, later files overriding earlier ones.
Create ``docker-compose.dev.yml`` with **only the differences**:

.. code-block:: yaml

   # Development overrides. Use together with the base file:
   #   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
   services:
     api:
       # Live reload: the host's src/ replaces the copy baked into the image.
       command:
         - uvicorn
         - bookshelf.main:app
         - --host=0.0.0.0
         - --port=8000
         - --reload
         - --reload-dir=/app/src
         - --log-level=debug
       volumes:
         - ./src:/app/src
       restart: "no"

     db:
       # Reach PostgreSQL from host tools (psql, DBeaver, pgAdmin) for debugging.
       # Bound to 127.0.0.1 so it is not reachable from the rest of the network.
       ports:
         - "127.0.0.1:5432:5432"

     cache:
       ports:
         - "127.0.0.1:6379:6379"

- The **bind mount** ``./src:/app/src`` hides the image's copy of the source behind your
  working tree.
- ``--reload`` makes uvicorn watch ``/app/src`` and restart its worker on every change.
- The debug ports for ``db`` and ``cache`` let you point a GUI client or a local
  ``psql`` at the containerized database — on loopback only.
- ``restart: "no"`` — a crash during development should stay crashed so you can read
  the traceback.

Start in dev mode, then edit ``src/bookshelf/main.py`` on the host — change the health
endpoint to return ``{"status": "ok", "mode": "dev"}``:

.. code-block:: bash

   $ docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
   $ curl -s localhost:8000/health
   {"status":"ok"}

   $ $EDITOR src/bookshelf/main.py      # edit and save

   $ curl -s localhost:8000/health
   {"status":"ok","mode":"dev"}

   $ docker compose logs api
   bookshelf-api-1  | INFO:     Started server process [8]
   bookshelf-api-1  | INFO:     Application startup complete.
   bookshelf-api-1  | INFO:     172.25.0.1:45422 - "GET /health HTTP/1.1" 200 OK
   bookshelf-api-1  | WARNING:  WatchFiles detected changes in 'src/bookshelf/main.py'. Reloading...
   bookshelf-api-1  | INFO:     Shutting down
   bookshelf-api-1  | INFO:     Finished server process [8]
   bookshelf-api-1  | INFO:     Started server process [11]
   bookshelf-api-1  | INFO:     Application startup complete.
   bookshelf-api-1  | INFO:     172.25.0.1:53284 - "GET /health HTTP/1.1" 200 OK

No rebuild.

How the two files are combined
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``-f docker-compose.yml -f docker-compose.dev.yml`` does **not** build or start two
stacks. Compose reads the files in order and **merges them into a single
configuration** before doing anything else. The second file is an overlay that only
lists what differs. ``up --build`` then acts on that one merged result.

The dev file never mentions ``build``, so after the merge there is still one ``api``
service with the base file's ``build: .``, and ``--build`` builds **one image**, the
same one production builds. In dev mode that image is simply run differently: the bind
mount hides its baked-in ``/app/src`` behind your working tree, and the overridden
``command`` starts uvicorn with ``--reload``.

When both files set the same key, the later file wins, but *how* depends on the kind
of key:

.. list-table::
   :header-rows: 1
   :widths: 34 30 36

   * - Kind of key
     - Merge behaviour
     - In BookShelf
   * - Single values (``command``, ``image``, ``restart``)
     - Replaced
     - Dev ``command`` replaces the default uvicorn command
   * - Mappings (``environment``, ``healthcheck``)
     - Merged key by key; same key takes the later value
     - Adding one variable in an override keeps all the others
   * - ``ports``
     - Combined
     - Dev adds ``127.0.0.1:5432:5432`` to ``db``
   * - ``volumes``
     - Combined, matched by container path
     - Dev adds ``./src:/app/src``; ``db`` keeps ``pgdata``

You never have to guess. ``config`` prints the single file Compose will actually use:

.. code-block:: bash

   $ docker compose -f docker-compose.yml -f docker-compose.dev.yml config
   ...
     api:
       build:
         context: /home/student/bookshelf
         dockerfile: Dockerfile
       command:
       - uvicorn
       - bookshelf.main:app
       - --host=0.0.0.0
       - --port=8000
       - --reload
       - --reload-dir=/app/src
       - --log-level=debug
       ...
       restart: "no"
       volumes:
       - type: bind
         source: /home/student/bookshelf/src
         target: /app/src
   ...

The ``build`` block comes from the base file. ``command``, ``restart`` and the bind
mount come from the override. An override *can* change how the image is built, for
example ``build: {context: ., dockerfile: Dockerfile.dev}``. Even then it is still one
build per service, just from a different Dockerfile.

.. admonition:: Observation:

   An alternative is to make the dev setup the default (``docker-compose.yml``
   + an automatically loaded ``docker-compose.override.yml``) and require ``-f`` for
   production. Either works. What matters is that the **production configuration is a
   file in the repository**, reviewed like code — not a set of flags someone types on
   the server. The solution's ``Makefile`` adds ``make up``, ``make dev`` and
   ``make down`` so nobody has to remember the ``-f`` flags.

-----

**Exercises**

#. With the stack running, use ``docker compose exec api python -c ...`` to resolve
   ``db`` and ``cache`` to IP addresses. Run ``docker compose down && docker compose up
   -d`` and resolve them again. Did the addresses change?

#. From your host, try ``nc -zv localhost 5432`` (or ``curl localhost:5432``). Explain
   the result by looking at the ``PORTS`` column of ``docker compose ps``.

#. Move the credentials into ``.env``: create ``.env.example`` and ``.env``, add ``.env``
   to ``.gitignore``, and update ``docker-compose.yml`` to the version above. Run
   ``docker compose config`` with and without the ``.env`` file. Then run
   ``git status`` and confirm ``.env`` is not listed.

#. Prove persistence. Create three books, then:

   .. code-block:: bash

      $ docker compose down
      $ docker compose up -d
      $ curl -s localhost:8000/books/ | python -m json.tool

   The books must still be there. Now run ``docker compose down -v``, start the stack
   again, and confirm the list is empty. Which command would you **never** run on a
   production host?

#. Create ``docker-compose.dev.yml`` as shown. Start in dev mode, edit a source file
   on the host, and verify with ``docker compose logs -f api`` that uvicorn reloads
   and the change is live without ``--build``.

#. In dev mode, connect to the containerized database from your host. Use
   ``psql postgresql://bookshelf:<password>@localhost:5432/bookshelf`` if you have a
   local ``psql``, or a GUI client such as DBeaver. Confirm you see the ``books`` table.

#. Precedence: run ``POSTGRES_DB=override docker compose config | grep POSTGRES_DB``.
   Which value wins — the shell or ``.env``? Check your answer against the precedence
   list above.
