.. _ch04_migrate_postgres:

Migrating BookShelf to PostgreSQL
==================================

.. note::

   The finished code for this page is in ``support/bookshelf-ch4-solution/``. If you get
   stuck, diff your ``database.py``, ``services.py`` and ``tests/conftest.py`` against it.

-----

Why Bother?
------------

SQLite has served the BookShelf API well: zero setup, a single file, perfect for tests.
It is the wrong choice for a production web service for three reasons:

- **One writer at a time.** SQLite locks the whole database file for each write. Under
  concurrent ``POST`` requests, writers queue behind each other and eventually fail
  with ``database is locked`` — the error you mocked in :ref:`ch03_mocking`.
- **One machine.** The database is a file on the API container's filesystem. Two API
  replicas cannot share it, and it disappears with the container unless a volume is
  carefully managed.
- **No operational tooling.** No network access for admin tools, no replication, no
  point-in-time recovery, no per-user permissions.

PostgreSQL solves all three. Containerization is what makes the switch cheap: an
hour ago "install and configure PostgreSQL" was a ticket for the ops team. Now it is
twelve lines of YAML that every developer runs locally.

-----

What Has to Change
-------------------

The service layer from :ref:`ch02_testable_code` takes a database connection as a
parameter, so the business logic does not care where the connection comes from. But
the SQL itself and the connection object are SQLite-specific:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * -
     - SQLite (``sqlite3``)
     - PostgreSQL (``psycopg``)
   * - Placeholders
     - ``WHERE id = ?``
     - ``WHERE id = %s``
   * - Auto-increment PK
     - ``INTEGER PRIMARY KEY AUTOINCREMENT``
     - ``SERIAL`` / ``GENERATED … AS IDENTITY``
   * - Last inserted ID
     - ``cursor.lastrowid``
     - ``INSERT … RETURNING id``
   * - Duplicate key error
     - ``sqlite3.IntegrityError``
     - ``psycopg.errors.UniqueViolation``
   * - ``LIKE`` case sensitivity
     - Case-*insensitive* (ASCII)
     - Case-*sensitive*
   * - Foreign keys
     - Off unless ``PRAGMA foreign_keys = ON``
     - Always enforced

Writing against both drivers directly means two versions of every query. Instead, use
**SQLAlchemy Core** — not the ORM, just its connection and SQL layer:

- one ``Connection`` API and one placeholder style (``:name``) for every database
- ``Table`` definitions that are rendered into the right DDL for each dialect
- one exception hierarchy (``sqlalchemy.exc.IntegrityError`` for both engines)
- connection pooling for PostgreSQL

You keep writing SQL. SQLAlchemy only removes the driver differences.

.. admonition:: Observation:

   Why not ``asyncpg``? It is fast, but it is PostgreSQL-only (no SQLite fallback for
   tests) and async-only, while the BookShelf routes are ordinary ``def`` functions that
   FastAPI runs in a thread pool. Switching to async is a separate refactor with its
   own trade-offs; do not couple it to a database migration.

-----

Dependencies
-------------

Add the two packages to ``pyproject.toml`` and regenerate the lockfile:

.. code-block:: toml

   dependencies = [
       "fastapi>=0.111",
       "uvicorn[standard]>=0.30",
       "httpx>=0.27",
       "sqlalchemy>=2.0",
       "psycopg[binary]>=3.1",
   ]

.. code-block:: bash

   $ pip install -e ".[dev]"
   $ pip-compile --strip-extras --output-file=requirements.lock pyproject.toml
   $ grep -E "^(sqlalchemy|psycopg)" requirements.lock
   psycopg==3.3.6
   psycopg-binary==3.3.6
   sqlalchemy==2.1.6

``psycopg[binary]`` is psycopg 3 with a bundled, pre-compiled ``libpq``, so neither your
laptop nor the Docker image needs PostgreSQL client libraries installed.

-----

The New database.py
--------------------

Replace ``src/bookshelf/database.py`` entirely:

.. code-block:: python

   import os
   from typing import Any

   from sqlalchemy import (
       CheckConstraint,
       Column,
       ForeignKey,
       Integer,
       MetaData,
       String,
       Table,
       Text,
       create_engine,
       event,
   )
   from sqlalchemy.engine import Connection, Engine

   DEFAULT_DATABASE_URL = "sqlite:///bookshelf.db"

   metadata = MetaData()

   books = Table(
       "books",
       metadata,
       Column("id", Integer, primary_key=True),
       Column("title", Text, nullable=False),
       Column("author", Text, nullable=False),
       Column("isbn", String(13), nullable=False, unique=True),
       Column("year", Integer, nullable=False),
   )

   reviews = Table(
       "reviews",
       metadata,
       Column("id", Integer, primary_key=True),
       Column(
           "book_id",
           Integer,
           ForeignKey("books.id", ondelete="CASCADE"),
           nullable=False,
       ),
       Column("rating", Integer, nullable=False),
       Column("text", Text, nullable=False),
       Column("reviewer", Text, nullable=False),
       CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
   )


   def normalize_database_url(url: str) -> str:
       """Map generic PostgreSQL URLs onto the psycopg 3 driver."""
       if url.startswith("postgres://"):
           url = "postgresql://" + url.removeprefix("postgres://")
       if url.startswith("postgresql://"):
           url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
       return url


   def _enable_sqlite_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
       dbapi_conn.execute("PRAGMA foreign_keys = ON")


   def make_engine(url: str) -> Engine:
       url = normalize_database_url(url)
       if url.startswith("sqlite"):
           engine = create_engine(url, connect_args={"check_same_thread": False})
           event.listen(engine, "connect", _enable_sqlite_foreign_keys)
           return engine
       return create_engine(url, pool_pre_ping=True)


   _engine: Engine | None = None


   def get_engine() -> Engine:
       global _engine
       if _engine is None:
           _engine = make_engine(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
       return _engine


   def reset_engine() -> None:
       """Drop the cached engine so the next call re-reads DATABASE_URL."""
       global _engine
       if _engine is not None:
           _engine.dispose()
       _engine = None


   def get_connection() -> Connection:
       return get_engine().connect()


   def _create_schema(conn: Connection) -> None:
       metadata.create_all(conn)
       conn.commit()


   def init_db() -> None:
       with get_connection() as conn:
           _create_schema(conn)

The important parts:

- **The schema is defined once**, as ``Table`` objects. ``metadata.create_all`` emits
  ``INTEGER PRIMARY KEY`` for SQLite and ``SERIAL`` for PostgreSQL. Like the old
  ``CREATE TABLE IF NOT EXISTS``, it skips tables that already exist.
- **normalize_database_url** accepts the standard ``postgresql://`` (and Heroku's
  legacy ``postgres://``) and selects the psycopg 3 driver. Without it, SQLAlchemy would
  look for the older ``psycopg2`` package. The ``DATABASE_URL`` in Compose stays
  driver-agnostic.
- **The engine is created lazily** from ``DATABASE_URL`` on first use and cached — one
  connection pool per process. ``reset_engine()`` exists for tests that change the
  variable.
- **pool_pre_ping=True** checks each pooled connection with a cheap round-trip before
  handing it out. When PostgreSQL restarts, pooled connections go stale; without
  pre-ping, the first request after a restart fails with a 500 and
  ``psycopg.errors.AdminShutdown: terminating connection due to administrator command``
  in the log. With it, the pool silently reconnects.
- ``get_connection()`` returns an ``engine.connect()`` context manager, so every router's
  ``with get_connection() as conn:`` block keeps working unchanged — and now actually
  *closes* the connection at the end (``sqlite3``'s context manager only committed).

-----

Porting services.py
--------------------

Every query changes in the same mechanical way: wrap the SQL in ``text()``, switch to
named ``:placeholders``, pass a dict, and read rows with ``.mappings()``. The function
signatures change only in the type of ``conn``:

.. code-block:: python

   from sqlalchemy import text
   from sqlalchemy.engine import Connection


   def create_book(conn: Connection, book: BookCreate) -> BookResponse:
       row = conn.execute(
           text(
               "INSERT INTO books (title, author, isbn, year) "
               "VALUES (:title, :author, :isbn, :year) "
               "RETURNING id, title, author, isbn, year"
           ),
           book.model_dump(),
       ).mappings().one()
       conn.commit()
       return BookResponse(**row)


   def get_book(conn: Connection, book_id: int) -> BookResponse | None:
       row = conn.execute(
           text("SELECT * FROM books WHERE id = :id"), {"id": book_id}
       ).mappings().first()
       return BookResponse(**row) if row else None

``RETURNING`` gives back the inserted row in the same statement, replacing the
``lastrowid`` + ``SELECT`` pair. Both PostgreSQL and SQLite (3.35+) support it.

``update_book`` builds its ``SET`` clause from named parameters:

.. code-block:: python

   set_clause = ", ".join(f"{k} = :{k}" for k in fields)
   result = conn.execute(
       text(f"UPDATE books SET {set_clause} WHERE id = :id"),  # noqa: S608
       {**fields, "id": book_id},
   )

The column names come from the fixed ``_UPDATABLE`` allow-list, never from user input,
so the f-string is safe; the *values* are still bound parameters.

In ``routers/books.py``, narrow the bare ``except Exception`` to the exception that
actually means "duplicate ISBN" — on both engines:

.. code-block:: python

   from sqlalchemy.exc import IntegrityError
   ...
           try:
               return services.create_book(conn, book)
           except IntegrityError:
               raise HTTPException(
                   status_code=409, detail="A book with this ISBN already exists"
               ) from None

With ``except Exception``, a dropped database connection would have been reported to
the client as "409 duplicate ISBN". Now it surfaces as a 500, which is the truth.

Port the remaining functions the same way (``list_books``, ``delete_book``,
``search_books``, ``get_top_books``, ``add_review``, ``list_reviews``). The tests will
tell you when you are done.

-----

Tests: SQLite by Default, PostgreSQL on Demand
-----------------------------------------------

Unit tests should stay fast and need no Docker. Make the shared fixture build an engine
from a URL — a temporary SQLite file unless ``TEST_DATABASE_URL`` says otherwise.
Replace the ``db_conn`` fixture at the top of ``tests/conftest.py``:

.. code-block:: python

   import itertools
   import os
   from collections.abc import Iterator
   from pathlib import Path

   import pytest
   from sqlalchemy.engine import Connection, Engine

   from bookshelf import services
   from bookshelf.database import make_engine, metadata
   from bookshelf.models import BookCreate, BookResponse, ReviewCreate, ReviewResponse


   @pytest.fixture
   def db_engine(tmp_path: Path) -> Iterator[Engine]:
       """A fresh, empty database per test.

       SQLite in a temp directory by default. Set TEST_DATABASE_URL to run the
       same tests against PostgreSQL (see docker-compose.test.yml).
       """
       url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
       engine = make_engine(url)
       metadata.drop_all(engine)
       metadata.create_all(engine)
       yield engine
       engine.dispose()


   @pytest.fixture
   def db_conn(db_engine: Engine) -> Iterator[Connection]:
       with db_engine.connect() as conn:
           yield conn

``drop_all`` + ``create_all`` gives every test an empty database. For SQLite the
directory is new anyway; for a shared PostgreSQL server it wipes the previous test's
data — the isolation principle from :ref:`ch03_test_isolation`.

The integration ``client`` fixture no longer monkeypatches a file path. It hands the
app the same per-test engine:

.. code-block:: python

   # tests/integration/conftest.py
   @pytest.fixture
   def client(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
       # Point the app at the per-test database instead of DATABASE_URL.
       monkeypatch.setattr("bookshelf.database._engine", db_engine)
       with TestClient(app) as c:
           yield c

Finally, replace ``sqlite3.Connection`` type hints with ``Connection`` in the test files,
and in ``tests/unit/test_mocking.py`` use ``MagicMock(spec=Connection)`` and
``sqlalchemy.exc.OperationalError`` instead of their ``sqlite3`` counterparts. Run the
suite:

.. code-block:: bash

   $ pytest -q
   collected 80 items

   tests/integration/test_books_api.py ...............                      [ 18%]
   tests/integration/test_reviews_api.py .....                              [ 25%]
   tests/unit/test_database.py .......                                      [ 33%]
   tests/unit/test_isbn_service.py .....                                    [ 40%]
   tests/unit/test_mocking.py ...                                           [ 43%]
   tests/unit/test_models.py .......                                        [ 52%]
   tests/unit/test_services.py .........................                    [ 83%]
   tests/unit/test_validation.py .............                              [100%]

   ============================== 80 passed in 0.65s ==============================

A Throwaway PostgreSQL for Tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Passing on SQLite proves the port is consistent with the old behaviour. It does not
prove the code works on PostgreSQL. Add ``docker-compose.test.yml``:

.. code-block:: yaml

   # Throwaway PostgreSQL for running the test suite against the real engine.
   name: bookshelf-test

   services:
     db-test:
       image: postgres:16-alpine
       environment:
         POSTGRES_USER: test
         POSTGRES_PASSWORD: test
         POSTGRES_DB: bookshelf_test
       ports:
         - "127.0.0.1:5433:5432"
       # Data lives in RAM: fast, and gone when the container stops.
       tmpfs:
         - /var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U test -d bookshelf_test"]
         interval: 2s
         timeout: 3s
         retries: 10

- ``name: bookshelf-test`` gives it its own Compose project, so it never collides with
  the main stack.
- Port **5433** on the host avoids clashing with a PostgreSQL you may already run on
  5432, and ``127.0.0.1:`` keeps it off the network.
- ``tmpfs`` puts the data directory in memory: faster, and nothing to clean up.

Start it, and point the suite at it. Suppose your port of ``search_books`` kept the
original query and just swapped the placeholders:

.. code-block:: python

   text("SELECT * FROM books WHERE title LIKE :pattern OR author LIKE :pattern"),
   {"pattern": f"%{query}%"},

.. code-block:: bash

   $ docker compose -f docker-compose.test.yml up -d --wait
    Container bookshelf-test-db-test-1  Started
    Container bookshelf-test-db-test-1  Healthy

   $ pytest -q                     # SQLite
   80 passed in 0.63s

   $ TEST_DATABASE_URL=postgresql://test:test@localhost:5433/bookshelf_test pytest
   ...
   collected 80 items

   tests/unit/test_database.py::test_search_is_case_insensitive FAILED      [ 33%]

   =================================== FAILURES ===================================
   _______________________ test_search_is_case_insensitive ________________________
   tests/unit/test_database.py:60: in test_search_is_case_insensitive
       assert len(services.search_books(db_conn, "clean")) == 1
   E   AssertionError: assert 0 == 1
   E    +  where 0 = len([])
   =========================== short test summary info ============================
   FAILED tests/unit/test_database.py::test_search_is_case_insensitive - Asserti...
   ========================= 1 failed, 79 passed in 3.73s =========================

The same code, the same tests, and a different answer. In SQLite, ``LIKE`` ignores case
for ASCII letters; in PostgreSQL it does not, so searching for ``clean`` no longer finds
*Clean Code*. Users would have reported it as "search is broken" the day after the
migration.

The regression test that caught it:

.. code-block:: python

   # tests/unit/test_database.py
   def test_search_is_case_insensitive(db_conn: Connection) -> None:
       # SQLite's LIKE ignores case; PostgreSQL's does not. This test pins the
       # behaviour so it holds on both engines.
       services.create_book(
           db_conn,
           BookCreate(
               title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
           ),
       )
       assert len(services.search_books(db_conn, "clean")) == 1
       assert len(services.search_books(db_conn, "ROBERT")) == 1

And the portable fix — lower-case both sides:

.. code-block:: python

   def search_books(conn: Connection, query: str) -> list[BookResponse]:
       # LIKE is case-insensitive in SQLite but case-sensitive in PostgreSQL.
       # Lower-casing both sides gives the same behaviour on both engines.
       rows = conn.execute(
           text(
               "SELECT * FROM books "
               "WHERE LOWER(title) LIKE :pattern OR LOWER(author) LIKE :pattern "
               "ORDER BY id"
           ),
           {"pattern": f"%{query.lower()}%"},
       ).mappings().all()
       return [BookResponse(**row) for row in rows]

Note the ``ORDER BY id``. Without an ``ORDER BY``, SQL does not define the order of
results. SQLite happens to return rows in insertion order; PostgreSQL usually does too
on a small fresh table, and then stops doing so after updates, deletes, or a
``VACUUM``. The solution adds an explicit order to every multi-row query, including a
tie-breaker in ``get_top_books`` (``ORDER BY COALESCE(AVG(r.rating), 0) DESC, b.id``) so
two books with the same average always come back in the same order. Pagination with
``LIMIT``/``OFFSET`` is meaningless without it.

With the fix:

.. code-block:: bash

   $ TEST_DATABASE_URL=postgresql://test:test@localhost:5433/bookshelf_test pytest -q
   80 passed in 6.08s

   $ docker compose -f docker-compose.test.yml down

The solution's ``Makefile`` wraps this in a ``test-pg`` target that starts the
container, runs the suite, and tears the container down even if tests fail.

.. admonition:: Observation:

   This is the strongest argument for testing against the real database engine at
   least somewhere in your pipeline. SQLite is a fine stand-in for most logic, and the
   fast default keeps the TDD loop from Chapter 2 tight. But dialect differences —
   case sensitivity, ordering, type coercion, constraint timing — are exactly the bugs
   a stand-in cannot catch. Chapter 5 runs ``make test-pg`` in CI using a PostgreSQL
   *service container*.

-----

Running the Stack on PostgreSQL
--------------------------------

Rebuild the image (the lockfile changed) and start the stack from
:ref:`ch04_compose`:

.. code-block:: bash

   $ docker compose up -d --build
   ...
    Container bookshelf-db-1  Healthy
    Container bookshelf-api-1  Starting
    Container bookshelf-api-1  Started

   $ docker compose ps
   NAME                IMAGE                COMMAND                  SERVICE   STATUS                   PORTS
   bookshelf-api-1     bookshelf-api        "uvicorn bookshelf.m…"   api       Up 4 seconds             0.0.0.0:8000->8000/tcp
   bookshelf-cache-1   redis:7-alpine       "docker-entrypoint.s…"   cache     Up 5 seconds             6379/tcp
   bookshelf-db-1      postgres:16-alpine   "docker-entrypoint.s…"   db        Up 5 seconds (healthy)   5432/tcp

   $ docker compose logs api
   bookshelf-api-1  | INFO:     Started server process [1]
   bookshelf-api-1  | INFO:     Waiting for application startup.
   bookshelf-api-1  | INFO:     Application startup complete.
   bookshelf-api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

Exercise every kind of endpoint:

.. code-block:: bash

   $ curl -s -X POST localhost:8000/books/ -H 'Content-Type: application/json' \
       -d '{"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008}'
   {"id":1,"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008}

   $ curl -s -X POST localhost:8000/books/ -H 'Content-Type: application/json' \
       -d '{"title":"Refactoring","author":"Martin Fowler","isbn":"9780201485677","year":1999}'
   {"id":2,"title":"Refactoring","author":"Martin Fowler","isbn":"9780201485677","year":1999}

   $ curl -s -X POST localhost:8000/books/1/reviews -H 'Content-Type: application/json' \
       -d '{"rating":5,"text":"Essential.","reviewer":"alice"}'
   {"id":1,"book_id":1,"rating":5,"text":"Essential.","reviewer":"alice"}

   $ curl -s -w ' [%{http_code}]\n' -X POST localhost:8000/books/ \
       -H 'Content-Type: application/json' \
       -d '{"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008}'
   {"detail":"A book with this ISBN already exists"} [409]

   $ curl -s 'localhost:8000/books/search?q=martin'
   [{"id":1,"title":"Clean Code","author":"Robert Martin","isbn":"9780132350884","year":2008},{"id":2,"title":"Refactoring","author":"Martin Fowler","isbn":"9780201485677","year":1999}]

Lower-case ``martin`` matches both *Robert Martin* and *Martin Fowler* — the fix works
on the real engine. Now confirm the data really is in PostgreSQL:

.. code-block:: bash

   $ docker compose exec db psql -U bookshelf -c '\dt'
             List of relations
    Schema |  Name   | Type  |   Owner
   --------+---------+-------+-----------
    public | books   | table | bookshelf
    public | reviews | table | bookshelf
   (2 rows)

   $ docker compose exec db psql -U bookshelf -c '\d books'
                                      Table "public.books"
    Column |         Type          | Collation | Nullable |              Default
   --------+-----------------------+-----------+----------+-----------------------------------
    id     | integer               |           | not null | nextval('books_id_seq'::regclass)
    title  | text                  |           | not null |
    author | text                  |           | not null |
    isbn   | character varying(13) |           | not null |
    year   | integer               |           | not null |
   Indexes:
       "books_pkey" PRIMARY KEY, btree (id)
       "books_isbn_key" UNIQUE CONSTRAINT, btree (isbn)
   Referenced by:
       TABLE "reviews" CONSTRAINT "reviews_book_id_fkey" FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE

``metadata.create_all`` translated ``Column("id", Integer, primary_key=True)`` into a
``SERIAL``-style column backed by ``books_id_seq``, plus the unique and foreign-key
constraints.

.. warning::

   ``create_all`` only creates *missing* tables. It never alters an existing one. The
   first time you add a column to ``books``, production will keep the old table and the
   API will fail with ``column "…" does not exist``. Real projects manage schema
   changes with versioned **migration scripts** — Alembic is the standard tool for
   SQLAlchemy. For this course, schema-on-startup is enough; just know where its limit
   is.

-----

**Exercises**

#. Add ``sqlalchemy`` and ``psycopg[binary]`` to ``pyproject.toml``, reinstall, and
   regenerate ``requirements.lock``. Replace ``database.py`` with the version above.

#. Port ``services.py`` to SQLAlchemy Core, one function at a time. After each
   function, run ``pytest tests/unit/test_services.py -q``. Update
   ``tests/conftest.py``, ``tests/integration/conftest.py`` and
   ``tests/unit/test_mocking.py`` as described. Finish with ``pytest`` passing on
   SQLite.

#. Add ``tests/unit/test_database.py`` with tests for ``normalize_database_url`` (use
   ``@pytest.mark.parametrize`` from :ref:`ch02_parametrize` for the four URL forms)
   and the case-insensitive search test.

#. Write ``docker-compose.test.yml``, start it, and run the suite with
   ``TEST_DATABASE_URL`` set. If everything passes, temporarily revert
   ``search_books`` to plain ``LIKE`` and confirm the PostgreSQL run fails while the
   SQLite run still passes. Restore the fix.

#. Rebuild and start the stack with ``docker compose up -d --build``. Verify all
   endpoints with ``curl`` or the Swagger UI at http://localhost:8000/docs: create,
   list, get, update, delete, search, top-rated, add and list reviews. Confirm with
   ``psql`` that the rows are in PostgreSQL.

#. Run ``pytest`` *without* Docker running (``docker compose down`` and
   ``unset TEST_DATABASE_URL``). Every test must still pass — the SQLite fallback is
   what keeps the inner TDD loop fast.

#. **(Optional)** Restart PostgreSQL under a running API with
   ``docker compose restart db``, then immediately ``curl localhost:8000/books/``.
   Now set ``pool_pre_ping=False`` in ``make_engine``, rebuild, and repeat. What does
   the first request after the restart return in each case?
