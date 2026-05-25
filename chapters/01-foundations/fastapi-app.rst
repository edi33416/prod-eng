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

Book Endpoints
---------------

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
