.. _ch01_fastapi_app:

Building the BookShelf API
============================

The BookShelf API is the running project for the entire course. This section walks through
building it from scratch: Pydantic models, SQLite database, FastAPI endpoints, and input
validation. The code you write here will be tested in Chapter 2, containerized in Chapter 4,
monitored in Chapter 7, and extended with AI features in Chapter 10.

.. admonition:: Crash Course: HTTP Methods & Status Codes
   :class: dropdown

   FastAPI is a web framework — it handles HTTP requests and produces responses. If you
   need a refresher on the protocol:

   **Methods:**

   - ``GET`` — retrieve a resource; safe and idempotent (no side effects, repeatable)
   - ``POST`` — create a new resource; returns the created object
   - ``PUT`` — replace a resource entirely; idempotent
   - ``PATCH`` — partially update a resource
   - ``DELETE`` — remove a resource; idempotent

   **Status codes used in this chapter:**

   .. list-table::
      :widths: 10 20 70
      :header-rows: 1

      * - Code
        - Name
        - When to use
      * - 200
        - OK
        - Successful GET, PUT, PATCH
      * - 201
        - Created
        - Successful POST (resource created)
      * - 204
        - No Content
        - Successful DELETE (no response body)
      * - 404
        - Not Found
        - Resource does not exist (e.g., ``GET /books/999``)
      * - 409
        - Conflict
        - Resource already exists (duplicate ISBN)
      * - 422
        - Unprocessable Entity
        - Request is well-formed but fails validation (FastAPI/Pydantic default)
      * - 500
        - Internal Server Error
        - Unhandled exception — should never reach users in production

   For a deeper dive, see: `MDN HTTP Status Codes <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status>`_

-----

FastAPI Basics
--------------

FastAPI is built on Starlette (async web framework) and Pydantic (data validation). Its
advantages for production use:

- **Type-driven:** request and response bodies are Pydantic models — validation is automatic
- **Auto-generated docs:** Swagger UI at ``/docs`` and ReDoc at ``/redoc`` — always accurate
- **Async-ready:** ``async def`` endpoints for I/O-bound work (database, network calls)
- **Testable:** ``httpx.AsyncClient`` lets you test endpoints without a running server (Chapter 3)

A minimal FastAPI app:

.. code-block:: python

   from fastapi import FastAPI

   app = FastAPI()

   @app.get("/")
   def root() -> dict[str, str]:
       return {"message": "Hello, World"}

Run it:

.. code-block:: bash

   $ uvicorn bookshelf.main:app --reload
   INFO:     Started server process [12345]
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)

``--reload`` watches source files and restarts on changes. Never use ``--reload`` in
production — it adds filesystem-watching overhead and is slower to start.

-----

Pydantic Models
----------------

Pydantic models define the shape of request and response data. FastAPI uses them for:

- **Request body validation** — reject invalid data before your handler runs
- **Response serialization** — control exactly which fields are returned
- **Auto-documentation** — generate the OpenAPI schema from the model fields automatically

Create ``src/bookshelf/models.py``:

.. code-block:: python

   from datetime import date

   from pydantic import BaseModel, Field, field_validator


   class BookCreate(BaseModel):
       title: str
       author: str
       isbn: str
       year: int

       @field_validator("isbn")
       @classmethod
       def validate_isbn(cls, v: str) -> str:
           digits = v.replace("-", "").replace(" ", "")
           if len(digits) not in (10, 13):
               raise ValueError("ISBN must be 10 or 13 digits")
           return digits

       @field_validator("year")
       @classmethod
       def validate_year(cls, v: int) -> int:
           current_year = date.today().year
           if v > current_year:
               raise ValueError(f"Year cannot be in the future (max: {current_year})")
           return v


   class BookResponse(BaseModel):
       id: int
       title: str
       author: str
       isbn: str
       year: int


   class BookUpdate(BaseModel):
       title: str | None = None
       author: str | None = None
       isbn: str | None = None
       year: int | None = None


   class ReviewCreate(BaseModel):
       rating: int = Field(ge=1, le=5, description="Star rating from 1 to 5")
       text: str
       reviewer: str


   class ReviewResponse(BaseModel):
       id: int
       book_id: int
       rating: int
       text: str
       reviewer: str

.. admonition:: Observation:

   ``BookCreate`` and ``BookResponse`` are separate models even though they share most
   fields. This is intentional: ``BookResponse`` includes ``id`` (assigned by the database)
   while ``BookCreate`` does not. Merging them would require ``id`` to be ``Optional[int]``,
   which then requires ``None``-checks in every handler. Separate models make the API
   contract explicit and keep validation logic clean.

-----

Database Setup
---------------

The BookShelf API uses SQLite via the standard library ``sqlite3`` module. SQLite is ideal
for development and low-to-medium traffic production services — no server to run, no
connection string to manage, the database is just a file.

.. admonition:: What is an ORM, and why aren't we using one?
   :class: dropdown

   An **Object-Relational Mapper (ORM)** is a library that maps database rows to Python
   objects and generates SQL from method calls, so you rarely write SQL directly. Instead
   of:

   .. code-block:: python

      conn.execute("SELECT * FROM books WHERE id = ?", (book_id,))

   you write something like:

   .. code-block:: python

      session.query(Book).filter(Book.id == book_id).first()

   Popular Python ORMs include **SQLAlchemy** (the most widely used), **Django ORM**
   (built into the Django framework), and **Tortoise ORM** (async-native).

   **What ORMs give you:**

   - Python objects instead of raw rows — no manual ``dict(row)`` conversions
   - Database-agnostic queries — switch from SQLite to PostgreSQL with a config change
   - Migration tools (e.g., Alembic for SQLAlchemy) that track schema changes as versioned files
   - Relationship handling — load a book's reviews via ``book.reviews`` without writing a JOIN

   **Why we are using raw ``sqlite3`` here:**

   This chapter is about project structure, tooling, and API design — not database
   abstractions. Raw ``sqlite3`` keeps the database layer transparent: you see exactly
   what SQL runs, and there is no ORM configuration to learn alongside everything else.

   In Chapter 4, the project migrates to PostgreSQL inside Docker. At that point the
   direct ``sqlite3`` calls become a limitation and SQLAlchemy is introduced as the
   production-grade replacement.

Create ``src/bookshelf/database.py``:

.. code-block:: python

   import sqlite3
   from pathlib import Path

   DB_PATH = Path(__file__).parent / "bookshelf.db"


   def get_connection() -> sqlite3.Connection:
       conn = sqlite3.connect(DB_PATH)
       conn.row_factory = sqlite3.Row       # rows act like dicts: row["title"]
       conn.execute("PRAGMA foreign_keys = ON")
       return conn


   def init_db() -> None:
       with get_connection() as conn:
           conn.execute("""
               CREATE TABLE IF NOT EXISTS books (
                   id     INTEGER PRIMARY KEY AUTOINCREMENT,
                   title  TEXT    NOT NULL,
                   author TEXT    NOT NULL,
                   isbn   TEXT    NOT NULL UNIQUE,
                   year   INTEGER NOT NULL
               )
           """)
           conn.execute("""
               CREATE TABLE IF NOT EXISTS reviews (
                   id       INTEGER PRIMARY KEY AUTOINCREMENT,
                   book_id  INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                   rating   INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                   text     TEXT    NOT NULL,
                   reviewer TEXT    NOT NULL
               )
           """)
           conn.commit()

``conn.row_factory = sqlite3.Row`` makes query results addressable by column name instead
of index. ``PRAGMA foreign_keys = ON`` must be called per connection — SQLite disables
foreign key enforcement by default for backwards compatibility.

-----

Database Transactions
----------------------

A **transaction** is a group of database operations that are treated as a single unit of
work. The database guarantees that either *all* operations in the transaction succeed and
are written to disk, or *none* of them are — there is no state where half the operations
completed and the rest did not.

This guarantee is essential for correctness. Consider adding a new book that comes with
an initial "staff pick" review:

.. code-block:: python

   conn.execute("INSERT INTO books ...", (...))
   conn.execute("INSERT INTO reviews ...", (...))   # references books.id

If the process crashes, the server loses power, or an exception is raised between the two
statements, you end up with a book that has no review — or, worse, a review pointing at a
book that was never committed. Without transactions, the database is left in a partially
written state that violates your own data integrity rules.

With a transaction, both inserts either land together or neither does.

ACID Properties
^^^^^^^^^^^^^^^^

Transactions provide four guarantees, abbreviated **ACID**:

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Property
     - Meaning
   * - **Atomicity**
     - All operations in the transaction succeed, or none are applied.
   * - **Consistency**
     - The database moves from one valid state to another — constraints are never violated mid-transaction.
   * - **Isolation**
     - Concurrent transactions do not see each other's uncommitted changes.
   * - **Durability**
     - Once committed, changes survive crashes and power loss.

For the BookShelf API, atomicity is the most immediately relevant: any operation that
touches more than one table must be wrapped in a single transaction.

Using Transactions in ``sqlite3``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``sqlite3`` module ties transaction control to Python's context manager protocol.
Using ``with conn:`` starts a transaction implicitly; the connection commits on a clean
exit and rolls back automatically if an exception is raised:

.. code-block:: python

   with get_connection() as conn:
       conn.execute("INSERT INTO books ...", (...))
       conn.execute("INSERT INTO reviews ...", (...))
       # both committed together when the block exits cleanly

   # if an exception is raised inside the block, sqlite3 rolls back both inserts

``conn.commit()`` called explicitly inside the block has the same effect as exiting
cleanly — it flushes the transaction immediately. You will see this pattern in the
endpoints when a write needs to be committed before a subsequent read in the same block:

.. code-block:: python

   cursor = conn.execute("INSERT INTO books ...", (...))
   conn.commit()                                          # flush before reading back
   row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()

Without the ``commit()`` here, the ``SELECT`` on the next line might not see the inserted
row, depending on the isolation level.

When Transactions Are Required
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use a single transaction any time a logical operation touches more than one statement and
partial completion would leave the data in an invalid or inconsistent state:

- **Multi-table writes** — inserting a parent and its children (book + initial review).
- **Read-modify-write** — reading a value, computing a new one, writing it back. Without
  a transaction, a concurrent request can modify the row between your read and your write.
- **Batch operations** — inserting or updating many rows at once. Wrapping them in one
  transaction is also dramatically faster than auto-committing each row individually,
  because each commit forces a disk sync.

Single-statement reads (``SELECT``) do not need explicit transaction management — they
are automatically consistent within a single statement.

.. warning::

   Keep transactions short. A transaction holds database locks for its entire duration.
   A long-running transaction — one that waits on a network call or sleeps between
   statements — blocks other writers and can cause timeouts under concurrent load. Do all
   computation *before* opening a write transaction, then write and commit as quickly as
   possible.

-----

Book Endpoints
---------------

FastAPI handlers receive input from two different places depending on the HTTP method and
the nature of the data:

**Request body** — used with ``POST``, ``PUT``, and ``PATCH``. Structured data sent in the
body of the HTTP request, encoded as JSON. Declared by typing a parameter as a Pydantic
model. FastAPI reads the body, validates it against the model, and rejects it with a 422
if validation fails — before your handler runs.

.. code-block:: python

   @router.post("/")
   def create_book(book: BookCreate) -> BookResponse:
       ...  # book.title, book.isbn, etc. are validated and typed

**Query parameters** — appended to the URL after ``?``. Used for filtering, sorting, and
pagination on ``GET`` requests. Declared with ``= Query(...)`` or just a plain default
value. They are part of the URL, not the body, so they are always strings on the wire —
FastAPI coerces and validates them.

.. code-block:: python

   @router.get("/")
   def list_books(
       offset: int = Query(default=0, ge=0),
       limit: int = Query(default=20, ge=1, le=100),
   ) -> list[BookResponse]:
       ...  # GET /books/?offset=20&limit=10

**Path parameters** — embedded in the URL path itself (e.g., ``/books/{book_id}``).
Declared by matching the parameter name to a ``{placeholder}`` in the route. FastAPI
extracts and coerces them automatically.

.. code-block:: python

   @router.get("/{book_id}")
   def get_book(book_id: int) -> BookResponse:
       ...  # GET /books/42  →  book_id = 42

.. admonition:: Observation:

   The choice between these is not arbitrary — it follows HTTP semantics. ``GET`` requests
   must not have a body (some clients and proxies discard it), so all input goes in the URL
   as query or path parameters. ``POST``/``PUT``/``PATCH`` carry structured data in the
   body because URLs have length limits and are logged in plain text — you do not want
   sensitive fields like passwords or large payloads appearing in server access logs.

Create ``src/bookshelf/routers/books.py``:

.. code-block:: python

   from fastapi import APIRouter, HTTPException, Query

   from bookshelf.database import get_connection
   from bookshelf.models import BookCreate, BookResponse, BookUpdate

   router = APIRouter(prefix="/books", tags=["books"])

   _UPDATABLE_FIELDS = {"title", "author", "isbn", "year"}


   @router.post("/", response_model=BookResponse, status_code=201)
   def create_book(book: BookCreate) -> BookResponse:
       with get_connection() as conn:
           try:
               cursor = conn.execute(
                   "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
                   (book.title, book.author, book.isbn, book.year),
               )
               conn.commit()
           except Exception:
               raise HTTPException(status_code=409, detail="A book with this ISBN already exists")
           row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
           return BookResponse(**dict(row))


   @router.get("/search", response_model=list[BookResponse])
   def search_books(
       q: str = Query(min_length=1, description="Search query for title or author"),
   ) -> list[BookResponse]:
       with get_connection() as conn:
           rows = conn.execute(
               "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
               (f"%{q}%", f"%{q}%"),
           ).fetchall()
           return [BookResponse(**dict(row)) for row in rows]


   @router.get("/", response_model=list[BookResponse])
   def list_books(
       offset: int = Query(default=0, ge=0),
       limit: int = Query(default=20, ge=1, le=100),
   ) -> list[BookResponse]:
       with get_connection() as conn:
           rows = conn.execute(
               "SELECT * FROM books LIMIT ? OFFSET ?", (limit, offset)
           ).fetchall()
           return [BookResponse(**dict(row)) for row in rows]


   @router.get("/{book_id}", response_model=BookResponse)
   def get_book(book_id: int) -> BookResponse:
       with get_connection() as conn:
           row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
           if row is None:
               raise HTTPException(status_code=404, detail="Book not found")
           return BookResponse(**dict(row))


   @router.put("/{book_id}", response_model=BookResponse)
   def update_book(book_id: int, updates: BookUpdate) -> BookResponse:
       fields = {
           k: v
           for k, v in updates.model_dump().items()
           if v is not None and k in _UPDATABLE_FIELDS
       }
       if not fields:
           raise HTTPException(status_code=422, detail="No fields provided for update")
       set_clause = ", ".join(f"{k} = ?" for k in fields)
       values = list(fields.values()) + [book_id]
       with get_connection() as conn:
           cursor = conn.execute(
               f"UPDATE books SET {set_clause} WHERE id = ?", values  # noqa: S608
           )
           conn.commit()
           if cursor.rowcount == 0:
               raise HTTPException(status_code=404, detail="Book not found")
           row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
           return BookResponse(**dict(row))


   @router.delete("/{book_id}", status_code=204)
   def delete_book(book_id: int) -> None:
       with get_connection() as conn:
           cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
           conn.commit()
           if cursor.rowcount == 0:
               raise HTTPException(status_code=404, detail="Book not found")

.. admonition:: Observation:

   The ``/search`` route is registered *before* ``/{book_id}`` in the router. This matters:
   FastAPI matches routes in the order they are registered. If ``/{book_id}`` appeared first,
   a request to ``GET /books/search`` would attempt to parse the string ``"search"`` as an
   integer ``book_id`` and return a 422 error. Always register specific paths before
   parameterized ones.

   A cleaner solution is to eliminate the ambiguity through API design rather than relying
   on registration order. Using a singular resource path for single-item operations —
   ``/book/{book_id}`` instead of ``/books/{book_id}`` — makes the conflict impossible:
   ``/books/search`` and ``/book/{book_id}`` are on different prefixes and will never
   collide, regardless of registration order. This also reflects a common REST convention:
   the collection lives at the plural (``/books``), and the individual resource at the
   singular (``/book/{id}``). The BookShelf API uses ``/books/{book_id}`` throughout for
   simplicity, but prefer the separated design in production APIs.

``LIKE`` Patterns and SQL Injection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The search query uses a SQL ``LIKE`` expression with ``%`` wildcards:

.. code-block:: python

   "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
   (f"%{q}%", f"%{q}%"),

``%`` is SQL's wildcard character: it matches any sequence of zero or more characters.
``f"%{q}%"`` wraps the search term with a ``%`` on each side, so ``LIKE "%pragmatic%"``
matches ``"The Pragmatic Programmer"``, ``"Pragmatic Thinking"``, and any other title
containing the word. Without the ``%`` characters, ``LIKE "pragmatic"`` would only match
rows where the entire field is exactly the string ``"pragmatic"``.

**User input and SQL injection**

The ``q`` parameter comes directly from the user. Any time user input is incorporated into
a database query, there is a risk of **SQL injection** — an attacker crafting input that
breaks out of the intended query and executes arbitrary SQL.

Consider what would happen if the query were built with string concatenation:

.. code-block:: python

   # NEVER do this
   conn.execute(f"SELECT * FROM books WHERE title LIKE '%{q}%'")

A user supplying ``q = "' OR '1'='1"`` would produce:

.. code-block:: text

   SELECT * FROM books WHERE title LIKE '%' OR '1'='1'%'

``'1'='1'`` is always true — this returns every row in the table regardless of the title.
With a more destructive payload, an attacker could drop tables or exfiltrate data.

The ``sqlite3`` module prevents this with **parameterised queries**: the ``?`` placeholder
and the values tuple are kept separate. The driver sends them to the database engine
independently — the engine treats the value as a literal string, never as SQL syntax,
no matter what characters it contains:

.. code-block:: python

   # Safe — q is always treated as a literal value, never as SQL
   conn.execute(
       "SELECT * FROM books WHERE title LIKE ?",
       (f"%{q}%",),
   )

.. warning::

   Always use parameterised queries (``?`` placeholders) for any value that originates
   outside your code — user input, API responses, file contents, environment variables.
   String formatting SQL is one of the most common and most damaging security mistakes in
   web applications. The ``S`` rule set in ruff (flake8-bandit) flags string-interpolated
   SQL as a security violation — this is one reason it is enabled in the project's ruff
   configuration.

-----

Review Endpoints
-----------------

Create ``src/bookshelf/routers/reviews.py``:

.. code-block:: python

   import sqlite3

   from fastapi import APIRouter, HTTPException

   from bookshelf.database import get_connection
   from bookshelf.models import ReviewCreate, ReviewResponse

   router = APIRouter(tags=["reviews"])


   def _require_book(conn: sqlite3.Connection, book_id: int) -> None:
       row = conn.execute("SELECT id FROM books WHERE id = ?", (book_id,)).fetchone()
       if row is None:
           raise HTTPException(status_code=404, detail="Book not found")


   @router.post("/books/{book_id}/reviews", response_model=ReviewResponse, status_code=201)
   def add_review(book_id: int, review: ReviewCreate) -> ReviewResponse:
       with get_connection() as conn:
           _require_book(conn, book_id)
           cursor = conn.execute(
               "INSERT INTO reviews (book_id, rating, text, reviewer) VALUES (?, ?, ?, ?)",
               (book_id, review.rating, review.text, review.reviewer),
           )
           conn.commit()
           row = conn.execute(
               "SELECT * FROM reviews WHERE id = ?", (cursor.lastrowid,)
           ).fetchone()
           return ReviewResponse(**dict(row))


   @router.get("/books/{book_id}/reviews", response_model=list[ReviewResponse])
   def list_reviews(book_id: int) -> list[ReviewResponse]:
       with get_connection() as conn:
           _require_book(conn, book_id)
           rows = conn.execute(
               "SELECT * FROM reviews WHERE book_id = ?", (book_id,)
           ).fetchall()
           return [ReviewResponse(**dict(row)) for row in rows]

-----

The FastAPI App
----------------

Wire everything together in ``src/bookshelf/main.py``:

.. code-block:: python

   from collections.abc import AsyncIterator
   from contextlib import asynccontextmanager

   from fastapi import FastAPI

   from bookshelf.database import init_db
   from bookshelf.routers import books, reviews


   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncIterator[None]:
       init_db()
       yield


   app = FastAPI(
       title="BookShelf API",
       description="A production-grade book catalog and review service.",
       version="0.1.0",
       lifespan=lifespan,
   )

   app.include_router(books.router)
   app.include_router(reviews.router)


   @app.get("/health", tags=["health"])
   def health_check() -> dict[str, str]:
       return {"status": "ok"}

The ``lifespan`` context manager runs ``init_db()`` at startup — creating the SQLite tables
if they do not exist. This is preferable to calling ``init_db()`` at module import time,
which breaks tests that mock the database (Chapter 3).

-----

Running the API
----------------

.. code-block:: bash

   $ uvicorn bookshelf.main:app --reload
   INFO:     Started server process [12345]
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)

.. admonition:: How the ``uvicorn`` command works
   :class: dropdown

   .. code-block:: text

      uvicorn bookshelf.main:app --reload

   **``uvicorn``** is an ASGI server — it handles the network layer: accepts TCP connections,
   parses HTTP requests, and calls your application code. It is to FastAPI what Apache or
   Nginx is to a PHP app, except it runs in the same process as your application.

   **``bookshelf.main:app``** is a Python import path with a specific format:
   ``<module>:<attribute>``. Uvicorn imports the module ``bookshelf.main`` and looks up the
   attribute named ``app`` — the ``FastAPI()`` instance defined in ``main.py``. This is why
   the package must be installed (``pip install -e .``) before running: uvicorn imports it
   the same way any Python code would.

   **``--reload``** watches the source tree for file changes and restarts the server
   automatically when it detects one. This works by spawning a child process that runs the
   actual server, with a parent process watching the filesystem. The reload happens in the
   child — the parent stays alive so the port is not released between restarts.

   Never use ``--reload`` in production. It adds filesystem-watching overhead, is slower to
   start, and the multi-process reload architecture is not designed for stability under load.
   In production, uvicorn is typically run with multiple worker processes managed by
   ``gunicorn`` (covered in Chapter 4):

   .. code-block:: bash

      # production invocation (preview — Chapter 4)
      $ gunicorn bookshelf.main:app \
            --worker-class uvicorn.workers.UvicornWorker \
            --workers 4 \
            --bind 0.0.0.0:8000

   **``--host`` and ``--port``** are omitted here, so uvicorn binds to ``127.0.0.1:8000``
   by default — localhost only, not reachable from other machines. Use
   ``--host 0.0.0.0`` to bind on all interfaces (needed inside Docker containers, where
   ``127.0.0.1`` only accepts connections from within the container itself).

Open ``http://127.0.0.1:8000/docs`` for the auto-generated Swagger UI. Every endpoint,
request body, and response model is documented from the code — it cannot drift from the
implementation.

Testing with ``curl``:

.. code-block:: bash

   # Create a book
   $ curl -s -X POST http://localhost:8000/books/ \
       -H "Content-Type: application/json" \
       -d '{"title": "The Pragmatic Programmer", "author": "David Thomas",
            "isbn": "9780135957059", "year": 1999}' | python -m json.tool
   {
       "id": 1,
       "title": "The Pragmatic Programmer",
       "author": "David Thomas",
       "isbn": "9780135957059",
       "year": 1999
   }

   # Add a review
   $ curl -s -X POST http://localhost:8000/books/1/reviews \
       -H "Content-Type: application/json" \
       -d '{"rating": 5, "text": "Essential reading.", "reviewer": "alice"}' \
       | python -m json.tool
   {
       "id": 1,
       "book_id": 1,
       "rating": 5,
       "text": "Essential reading.",
       "reviewer": "alice"
   }

   # Search books
   $ curl -s "http://localhost:8000/books/search?q=Pragmatic" | python -m json.tool
   [{"id": 1, "title": "The Pragmatic Programmer", ...}]

   # Get a non-existent book — expect 404
   $ curl -s http://localhost:8000/books/999
   {"detail": "Book not found"}

-----

**Exercise 1 — Implement and Verify All Endpoints**

#. Implement all files: ``models.py``, ``database.py``, ``routers/__init__.py``,
   ``routers/books.py``, ``routers/reviews.py``, and ``main.py`` using the code shown above.

#. Start the server and open the Swagger UI at ``http://localhost:8000/docs``. Use the
   interactive "Try it out" button to test each endpoint.

#. Verify the following scenarios with ``curl`` or the Swagger UI:

   - ``POST /books/`` — create two books with valid data
   - ``GET /books/`` — list all books (returns 2)
   - ``GET /books/1`` — get book by ID
   - ``GET /books/999`` — expect 404 with ``"detail": "Book not found"``
   - ``PUT /books/1`` — update only the title (send ``{"title": "New Title"}``)
   - ``POST /books/1/reviews`` — add a review
   - ``GET /books/1/reviews`` — list reviews for book 1
   - ``GET /books/search?q=<author-name>`` — search by author
   - ``DELETE /books/1`` — delete a book
   - ``GET /health`` — expect ``{"status": "ok"}``

**Exercise 2 — Verify Input Validation**

Pydantic handles validation automatically. Confirm it works correctly:

#. Submit a book with an invalid ISBN:

   .. code-block:: bash

      $ curl -s -X POST http://localhost:8000/books/ \
          -H "Content-Type: application/json" \
          -d '{"title": "Bad Book", "author": "Test", "isbn": "123", "year": 2020}'

   Expected: ``422 Unprocessable Entity`` with a ``detail`` array describing which field
   failed and why.

#. Submit a book with a future year:

   .. code-block:: bash

      $ curl -s -X POST http://localhost:8000/books/ \
          -H "Content-Type: application/json" \
          -d '{"title": "Future Book", "author": "Test", "isbn": "9780135957059", "year": 2099}'

   Expected: 422 with a message about the year constraint.

#. Submit a review with a rating of 6:

   .. code-block:: bash

      $ curl -s -X POST http://localhost:8000/books/1/reviews \
          -H "Content-Type: application/json" \
          -d '{"rating": 6, "text": "Off the charts!", "reviewer": "bob"}'

   Expected: 422 because ``rating`` must be between 1 and 5 (``ge=1, le=5``).

#. Verify all three return meaningful error messages that identify the failing field and
   describe the constraint violation.

.. admonition:: Observation:

   The auto-generated ``/docs`` page displays the full JSON Schema for every request model,
   including validation constraints (``ge=1``, ``le=5``, ``minLength=10``). This means API
   documentation is always accurate because it *is* the code — there is no separate
   documentation file to keep in sync.

.. warning::

   The SQLite database file is created in ``src/bookshelf/bookshelf.db`` by default. This
   works for development but is wrong for production — the database would live inside the
   installed package directory. In Chapter 4, you will configure the database path via an
   environment variable and mount it as a Docker volume. For now, add ``*.db`` to
   ``.gitignore``.
