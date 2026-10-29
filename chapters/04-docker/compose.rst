.. _ch04_compose:

Docker Compose for Multi-Container Apps
========================================

One Service Is Never One Container
-----------------------------------

The BookShelf API is about to get a real database (PostgreSQL) and a cache (Redis).
With plain ``docker run``, starting that stack by hand looks like this:

.. code-block:: bash

   $ docker network create bookshelf-net
   $ docker volume create pgdata
   $ docker run -d --name db --network bookshelf-net \
       -e POSTGRES_USER=bookshelf -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=bookshelf \
       -v pgdata:/var/lib/postgresql/data postgres:16-alpine
   $ docker run -d --name cache --network bookshelf-net redis:7-alpine
   $ sleep 5   # hope PostgreSQL is ready by now...
   $ docker run -d --name api --network bookshelf-net -p 8000:8000 \
       -e DATABASE_URL=postgresql://bookshelf:secret@db:5432/bookshelf bookshelf:v2

Seven commands, an ordering dependency enforced by ``sleep``, and configuration that
lives only in your shell history. Nobody else on the team can reproduce it, and you
will not remember the flags in a month.

**Docker Compose** replaces this with a declarative file: you describe *what* the stack
looks like, and ``docker compose up`` makes it so.

-----

The Compose File
-----------------

Create ``docker-compose.yml`` in the project root:

.. code-block:: yaml

   services:
     api:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DATABASE_URL=postgresql://bookshelf:secret@db:5432/bookshelf
         - REDIS_URL=redis://cache:6379
       depends_on:
         db:
           condition: service_healthy
         cache:
           condition: service_started

     db:
       image: postgres:16-alpine
       environment:
         POSTGRES_USER: bookshelf
         POSTGRES_PASSWORD: secret
         POSTGRES_DB: bookshelf
       volumes:
         - pgdata:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U bookshelf"]
         interval: 5s
         timeout: 5s
         retries: 5

     cache:
       image: redis:7-alpine

   volumes:
     pgdata:

Each key under ``services`` becomes one container:

- ``api`` — ``build: .`` builds the image from the ``Dockerfile`` in this directory.
  ``ports`` publishes 8000 on the host. ``environment`` sets ``DATABASE_URL`` — note
  that the host part is ``db``, the *service name*.
- ``db`` — the official PostgreSQL image. Its entrypoint reads ``POSTGRES_USER``,
  ``POSTGRES_PASSWORD`` and ``POSTGRES_DB`` on first start and creates that user and
  database. ``volumes`` keeps the data directory in a named volume.
- ``cache`` — Redis with default settings. The API does not use it yet; it is part of
  the stack the later chapters build on (LiteLLM's response cache in Chapter 11).

Note what is **not** there: no ``ports`` for ``db`` or ``cache``. They are reachable
from ``api`` over the Compose network, but not from the host or the outside world.

.. warning::

   ``POSTGRES_PASSWORD: secret`` in a committed file is acceptable for the first five
   minutes of a tutorial and nowhere else. :ref:`ch04_networking_volumes` moves it into
   an uncommitted ``.env`` file.

Reaching Services by Name
^^^^^^^^^^^^^^^^^^^^^^^^^^

Look at the hostnames in the API's configuration:

.. code-block:: yaml

   DATABASE_URL=postgresql://bookshelf:secret@db:5432/bookshelf
   REDIS_URL=redis://cache:6379

``db`` and ``cache`` are not real hostnames anywhere on the internet. They are the
**service names** you chose under ``services:``. They work because Compose puts every
service of the project on one shared private network, and Docker runs a small DNS
server on that network that answers each service name with that container's current IP
address. When the API connects to ``db``, it asks that DNS server and gets
PostgreSQL's address. Rename the service to ``postgres`` and the URL must say
``@postgres:5432``.

Two consequences trip people up:

- **localhost means "this container".** Inside ``api``, ``localhost:5432`` is the API
  container itself, where nothing listens on 5432. Every container has its own network
  namespace, so a service is always reached by its *name*, never by ``localhost``.
- **Use the container port, not a published one.** ``5432`` and ``6379`` are the ports
  the servers listen on *inside* their containers. Traffic between services stays on
  the private network and never goes through ``ports:``, which is why ``db`` and
  ``cache`` need no published ports at all.

How that network looks from the inside is covered in :ref:`ch04_networking_volumes`.

Volumes
^^^^^^^^

``volumes`` appears twice in the file, and the two halves work together:

.. code-block:: yaml

   services:
     db:
       volumes:
         - pgdata:/var/lib/postgresql/data   # 2. mount it: NAME:PATH-IN-CONTAINER

   volumes:
     pgdata:                                 # 1. declare a named volume

- The **top-level** ``volumes:`` declares the named volumes the project owns. Compose
  creates each one on the first ``up`` and prefixes it with the project name, so
  ``pgdata`` becomes ``bookshelf_pgdata``. A service that uses an undeclared name is a
  configuration error:
  ``service "db" refers to undefined volume pgdata: invalid compose project``.
- The **service-level** entry mounts that volume into the container. It is the same
  ``NAME:PATH`` form as ``docker run -v`` from :ref:`ch04_docker_basics`. The path is
  not arbitrary. ``/var/lib/postgresql/data`` is where the PostgreSQL image keeps its
  database files (its ``PGDATA``), so everything the database writes lands in the
  volume instead of the container's writable layer.

That matters because Compose **recreates** containers freely, for example whenever
the image or the service's configuration changes on the next ``up``. The ``db``
container is disposable; ``bookshelf_pgdata`` is not. How long the data really
survives, and when it is deleted, is the subject of :ref:`ch04_networking_volumes`.

depends_on and Health Checks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``depends_on`` controls **start order**. By itself (or with
``condition: service_started``), it only waits until the dependency's container has
*started* — and PostgreSQL takes a few seconds after starting before it accepts
connections. An API that connects during startup would crash in that window.

``condition: service_healthy`` waits until the dependency's **healthcheck** passes.
``pg_isready`` asks the server whether it is accepting connections. The other three
keys decide how Docker turns individual checks into a health status:

- ``interval: 5s`` sets how often the check runs.
- ``timeout: 5s`` sets how long one check may take. A check that hangs longer counts as a
  failure.
- ``retries: 5`` sets how many **consecutive** failures it takes to mark the container
  ``unhealthy``.

A container starts in the ``starting`` state. The first successful check makes it
``healthy``, and any success resets the failure count. With the values above, a
PostgreSQL that never comes up is declared ``unhealthy`` after about 5 × 5 s = 25
seconds. Compose then gives up on everything that depends on it. Here is a database
whose check always fails, with ``interval: 2s`` and ``retries: 3``:

.. code-block:: yaml

   # hc/docker-compose.yml — a throwaway experiment, not part of BookShelf
   services:
     app:
       image: alpine:3.20
       command: sleep 3600
       depends_on:
         db:
           condition: service_healthy
     db:
       image: alpine:3.20
       command: sleep 3600
       healthcheck:
         test: ["CMD", "false"]     # always exits 1: a check that never passes
         interval: 2s
         timeout: 1s
         retries: 3

.. code-block:: bash

   $ docker compose up -d
    Container hc-db-1  Started
    Container hc-db-1  Waiting
    Container hc-db-1  Error
   dependency failed to start: container hc-db-1 is unhealthy

   $ docker compose ps -a
   NAME       IMAGE         COMMAND        SERVICE   STATUS                     PORTS
   hc-app-1   alpine:3.20   "sleep 3600"   app       Created
   hc-db-1    alpine:3.20   "sleep 3600"   db        Up 6 seconds (unhealthy)

Three failed checks, about six seconds, and the dependent ``app`` container is created
but never started. ``retries`` is therefore a trade-off. Set it too low and a database
that is merely slow to start (the first start runs ``initdb``, which takes longer on a
slow disk) is declared dead. Set it too high and a genuinely broken stack takes minutes
to report the failure. If first-time initialization is the slow part, add
``start_period: 30s`` instead. Failures during the start period do not count towards
``retries``, so you get a grace period at startup without slowing down failure
detection later.

.. admonition:: Observation:

   ``depends_on`` only helps at startup. If the database restarts while the API is
   running, the API must cope on its own — by reconnecting, not by crashing. You will
   see the pool setting that handles this in :ref:`ch04_migrate_postgres`, and build
   proper readiness endpoints in Chapter 9.

-----

Bringing the Stack Up
----------------------

.. code-block:: bash

   $ docker compose up -d
   ...
    Network bookshelf_default  Created
    Volume "bookshelf_pgdata"  Created
    Container bookshelf-cache-1  Created
    Container bookshelf-db-1  Created
    Container bookshelf-api-1  Created
    Container bookshelf-cache-1  Started
    Container bookshelf-db-1  Started
    Container bookshelf-db-1  Waiting
    Container bookshelf-db-1  Healthy
    Container bookshelf-api-1  Starting
    Container bookshelf-api-1  Started

The first ``up`` also builds the ``api`` image (the elided ``...``), tagged
``bookshelf-api`` after the project and service names.

Compose prefixed everything with the **project name**, which defaults to the directory
name (``bookshelf``). It created a network, a volume, and three containers — and it
waited for ``db`` to become ``Healthy`` before starting ``api``.

Check the state of the stack:

.. code-block:: bash

   $ docker compose ps -a
   NAME                IMAGE                COMMAND                  SERVICE   STATUS                     PORTS
   bookshelf-api-1     bookshelf-api        "uvicorn bookshelf.m…"   api       Exited (1) 2 seconds ago
   bookshelf-cache-1   redis:7-alpine       "docker-entrypoint.s…"   cache     Up 8 seconds               6379/tcp
   bookshelf-db-1      postgres:16-alpine   "docker-entrypoint.s…"   db        Up 8 seconds (healthy)     5432/tcp

The database is healthy. The API has **exited with status 1**. Ask it why:

.. code-block:: bash

   $ docker compose logs api
   bookshelf-api-1  |   File "/app/src/bookshelf/main.py", line 6, in <module>
   bookshelf-api-1  |     from bookshelf.database import init_db
   bookshelf-api-1  |   File "/app/src/bookshelf/database.py", line 16, in <module>
   bookshelf-api-1  |     DB_PATH = _sqlite_path(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
   bookshelf-api-1  |               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   bookshelf-api-1  |   File "/app/src/bookshelf/database.py", line 10, in _sqlite_path
   bookshelf-api-1  |     raise ValueError(
   bookshelf-api-1  | ValueError: Unsupported DATABASE_URL scheme 'postgresql': only sqlite:/// is supported

This is the fail-fast check you added in :ref:`ch04_multistage` doing its job. The
container wiring is correct — the API received a PostgreSQL URL — but the application
only speaks SQLite. Without the check, the URL would have been treated as a file path
and the API would have died with the baffling ``unable to open database file`` — or,
had the code simply ignored ``DATABASE_URL``, it would have started happily on a SQLite
file inside the container, and you would have found out when the data vanished on the
next deploy.

Teaching the API PostgreSQL is the subject of :ref:`ch04_migrate_postgres`. First, get
familiar with the database you have just started.

.. admonition:: Crash Course: PostgreSQL Essentials
   :class: dropdown

   PostgreSQL is a client-server database: a server process listens on TCP port 5432
   and clients connect over the network with a username and password. (SQLite, by
   contrast, is a library that reads and writes a local file.)

   **Connection strings** pack all connection parameters into one URL:

   .. code-block:: text

      postgresql://bookshelf:secret@db:5432/bookshelf
      └─scheme──┘ └─user──┘ └pass┘ └host┘└port┘└─database┘

   Special characters in the password (``@``, ``:``, ``/``, ``#``) must be
   percent-encoded, or the URL is parsed incorrectly.

   **Health check** — is the server accepting connections?

   .. code-block:: bash

      $ docker compose exec db pg_isready -U bookshelf
      /var/run/postgresql:5432 - accepting connections

   **psql** is the interactive client. Inside the ``db`` container it is already
   installed and authenticates over a local socket:

   .. code-block:: bash

      $ docker compose exec db psql -U bookshelf
      bookshelf=# \l bookshelf          -- describe the database
      bookshelf=# \dt                   -- list tables
      Did not find any relations.
      bookshelf=# \q                    -- quit

   Other useful meta-commands: ``\d books`` (describe a table), ``\du`` (roles),
   ``\x`` (toggle vertical output for wide rows), ``\?`` (help).

   **Basic SQL** works as you expect from SQLite, with stricter types:

   .. code-block:: bash

      $ docker compose exec -T db psql -U bookshelf <<'EOF'
      CREATE TABLE scratch (id SERIAL PRIMARY KEY, note TEXT NOT NULL);
      INSERT INTO scratch (note) VALUES ('hello from psql'), ('second row');
      SELECT * FROM scratch;
      DROP TABLE scratch;
      EOF
      CREATE TABLE
      INSERT 0 2
       id |      note
      ----+-----------------
        1 | hello from psql
        2 | second row
      (2 rows)

      DROP TABLE

   ``SERIAL`` is PostgreSQL's auto-incrementing integer (backed by a *sequence*); it
   replaces SQLite's ``INTEGER PRIMARY KEY AUTOINCREMENT``. ``-T`` disables TTY
   allocation so a heredoc can be piped into ``psql``.

   For a deeper dive, see: `PostgreSQL tutorial <https://www.postgresql.org/docs/16/tutorial.html>`_

-----

Everyday Compose Commands
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Command
     - Purpose
   * - ``docker compose up -d``
     - Create/start all services in the background
   * - ``docker compose up -d --build``
     - Rebuild images first (after code changes)
   * - ``docker compose ps [-a]``
     - Service status, including health
   * - ``docker compose logs -f api``
     - Follow one service's logs (omit the name for all)
   * - ``docker compose exec db psql -U bookshelf``
     - Run a command in a running service
   * - ``docker compose run --rm api python -c '…'``
     - One-off container with the service's config
   * - ``docker compose restart api``
     - Restart a service without recreating it
   * - ``docker compose down``
     - Stop and remove containers and the network (volumes are kept)
   * - ``docker compose down -v``
     - … and also delete named volumes — **destroys data**
   * - ``docker compose config``
     - Print the fully resolved configuration

Compose commands operate on the project in the current directory. Run them from the
directory containing ``docker-compose.yml``, or pass ``-f`` / ``-p``.

-----

**Exercises**

#. Write the ``docker-compose.yml`` shown above. Start the stack with
   ``docker compose up -d`` and watch the output: in what order are the containers
   started, and which one is reported as ``Healthy``?

#. Run ``docker compose ps -a`` and ``docker compose logs api``. Confirm the API exits
   with the ``Unsupported DATABASE_URL scheme 'postgresql'`` error. Explain in one
   sentence why this is better than the API starting successfully.

#. Connect to the database with ``docker compose exec db psql -U bookshelf``. Create a
   table, insert two rows, query them, and drop the table. Use ``\dt`` before and after.

#. Change ``depends_on.db.condition`` to ``service_started`` and run
   ``docker compose down && docker compose up -d``. Look at the timing in the output.
   Why would this be a problem for an API that *does* connect to PostgreSQL on startup?
   Restore ``service_healthy``.

#. Run ``docker compose exec cache redis-cli ping``. Then try ``redis-cli ping`` on your
   host (if installed) or ``nc -zv localhost 6379``. Why does one work and not the other?

#. Leave the stack running — the next page builds on it. When you want to stop it,
   use ``docker compose down`` (not ``down -v``).
