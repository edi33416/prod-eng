.. _ch02_testable_code:

Writing Testable Code
======================

The biggest obstacle to testing is not writing the tests — it is code that is hard to test.
A function that talks directly to a production database, sends emails, or reads from the
filesystem cannot be tested in isolation. This section shows how to structure code so tests
can exercise it without real infrastructure.

-----

Dependency Injection
---------------------

Dependency injection (DI) means providing a component's dependencies from the outside
instead of creating them internally. In Python, this is usually just passing arguments.

**Without DI (hard to test):**

.. code-block:: python

   def send_welcome_email(user_id: int) -> None:
       db = PostgreSQL("postgresql://prod-server/db")  # hardcoded
       smtp = SMTP("mail.company.com")                 # hardcoded
       user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
       smtp.send(user.email, "Welcome!")

To test this, you need a real PostgreSQL server and a real SMTP server. You cannot run
it in a test without sending real emails.

**With DI (testable):**

.. code-block:: python

   def send_welcome_email(db: Database, smtp: SMTP, user_id: int) -> None:
       user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
       smtp.send(user.email, "Welcome!")

Now a test can pass in a fake database and a fake SMTP client. Production code passes
in real ones. The business logic is identical — only the dependencies differ.

**In Python, DI is just function parameters.** You don't need a framework.

For a deeper dive, see: `Martin Fowler on Dependency Injection <https://martinfowler.com/articles/injection.html>`_

-----

The Core Principle: Separate Logic from Infrastructure
-------------------------------------------------------

Every application has two fundamentally different kinds of code:

**Business logic** — what the application *does*:

- Validates that an ISBN has 10 or 13 digits
- Calculates the average rating of a book's reviews
- Determines which books match a search query

Business logic is pure: given the same inputs, it always produces the same outputs.
It does not touch the database, the network, or the filesystem.

**Infrastructure** — how the application talks to the world:

- Reads and writes to a SQLite database
- Sends HTTP responses
- Reads environment variables

Infrastructure has side effects. It is hard to test in isolation because it requires external
systems to be running.

The principle is simple: **keep business logic and infrastructure in separate functions.**
Business logic becomes trivially testable (pure functions). Infrastructure can be tested
at the integration level (Chapter 3) where external systems are either real or stubbed.

-----

Contracts, Not Defenses
------------------------

There are two instincts when writing a function that could receive bad input:

**Defensive programming** — handle everything that could go wrong inside the function:

.. code-block:: python

   def calculate_average_rating(ratings):
       try:
           if ratings is None:
               ratings = []
           cleaned = []
           for r in ratings:
               try:
                   cleaned.append(int(r))
               except (TypeError, ValueError):
                   continue   # silently ignore bad values
           if not cleaned:
               return None
           return sum(cleaned) / len(cleaned)
       except Exception:
           return None   # never crash

**Contract programming** — define what the function expects, assert it, and fail fast if
the contract is broken:

.. code-block:: python

   def calculate_average_rating(ratings: list[int]) -> float | None:
       assert isinstance(ratings, list), f"expected list, got {type(ratings)}"
       assert all(isinstance(r, int) for r in ratings), "ratings must be integers"
       if not ratings:
           return None
       return sum(ratings) / len(ratings)

The defensive version silently swallows a ``None`` argument, coerces strings to integers,
and catches all exceptions — producing a ``None`` result regardless of what went wrong.
A caller passing the wrong type gets back a plausible-looking answer and has no indication
anything was wrong.

The contract version crashes immediately with a clear message if a caller passes ``None``
or a list of strings. **This is correct behavior.** A bug in the caller is exposed at
the point where the contract is broken, not silently corrupted and surfaced three layers
up — or never.

**Where to validate defensively.** Input validation belongs at system boundaries: HTTP
request parameters, file contents, external API responses. These come from outside the
system and cannot be trusted. Inside the system — function calls between modules you
control — trust the contract. Your tests verify that callers pass valid arguments; there
is no need to re-validate what you have already asserted.

.. admonition:: Observation:

   A test suite and a contract-based codebase reinforce each other. Tests verify that each
   function is called correctly; assertions inside functions verify the same at runtime.
   When a contract is breached in a test, the assertion fires at exactly the right line.
   In a defensive codebase, the same bug would silently return ``None`` — and you would
   spend time tracing where that ``None`` came from.

-----

Before: The Ch1 Router (Logic Tangled with Infrastructure)
------------------------------------------------------------

In Chapter 1, the router functions did everything directly:

.. code-block:: python

   # routers/books.py — Ch1 version (hard to unit test)
   @router.post("/", response_model=BookResponse, status_code=201)
   def create_book(book: BookCreate) -> BookResponse:
       with get_connection() as conn:        # ← infrastructure: opens DB connection
           try:
               cursor = conn.execute(        # ← infrastructure: SQL
                   "INSERT INTO books ...", ...)
               conn.commit()
           except Exception:
               raise HTTPException(...)      # ← HTTP concern
           row = conn.execute(...).fetchone()
           return BookResponse(**dict(row))  # ← data transformation

To test this, you would need to call it through the FastAPI framework with a real HTTP
request — no way to call ``create_book`` without spinning up a server and a database.
That is an integration test, not a unit test.

-----

After: The Services Layer
--------------------------

Extract all business logic and database operations into ``src/bookshelf/services.py``.
Each function accepts a database connection as its first argument — this is the injection
point that makes tests possible.

.. code-block:: python

   # src/bookshelf/services.py
   import sqlite3

   from bookshelf.models import BookCreate, BookResponse, BookUpdate, ReviewCreate, ReviewResponse


   def validate_isbn(isbn: str) -> bool:
       digits = isbn.replace("-", "").replace(" ", "")
       return len(digits) in (10, 13) and digits.isdigit()


   def calculate_average_rating(ratings: list[int]) -> float | None:
       if not ratings:
           return None
       return sum(ratings) / len(ratings)


   def create_book(conn: sqlite3.Connection, book: BookCreate) -> BookResponse:
       cursor = conn.execute(
           "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
           (book.title, book.author, book.isbn, book.year),
       )
       conn.commit()
       row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
       return BookResponse(**dict(row))


   def get_book(conn: sqlite3.Connection, book_id: int) -> BookResponse | None:
       row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
       return BookResponse(**dict(row)) if row else None


   def list_books(
       conn: sqlite3.Connection, offset: int = 0, limit: int = 20
   ) -> list[BookResponse]:
       rows = conn.execute(
           "SELECT * FROM books LIMIT ? OFFSET ?", (limit, offset)
       ).fetchall()
       return [BookResponse(**dict(row)) for row in rows]


   def update_book(
       conn: sqlite3.Connection, book_id: int, updates: BookUpdate
   ) -> BookResponse | None:
       _UPDATABLE = {"title", "author", "isbn", "year"}
       fields = {k: v for k, v in updates.model_dump().items() if v is not None and k in _UPDATABLE}
       if not fields:
           return get_book(conn, book_id)
       set_clause = ", ".join(f"{k} = ?" for k in fields)
       values = list(fields.values()) + [book_id]
       cursor = conn.execute(
           f"UPDATE books SET {set_clause} WHERE id = ?", values  # noqa: S608
       )
       conn.commit()
       return get_book(conn, book_id) if cursor.rowcount > 0 else None


   def delete_book(conn: sqlite3.Connection, book_id: int) -> bool:
       cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
       conn.commit()
       return cursor.rowcount > 0


   def search_books(conn: sqlite3.Connection, query: str) -> list[BookResponse]:
       rows = conn.execute(
           "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
           (f"%{query}%", f"%{query}%"),
       ).fetchall()
       return [BookResponse(**dict(row)) for row in rows]


   def get_top_books(conn: sqlite3.Connection, n: int) -> list[BookResponse]:
       if n <= 0:
           return []
       rows = conn.execute(
           """
           SELECT b.id, b.title, b.author, b.isbn, b.year
           FROM books b
           LEFT JOIN reviews r ON b.id = r.book_id
           GROUP BY b.id
           ORDER BY COALESCE(AVG(r.rating), 0) DESC
           LIMIT ?
           """,
           (n,),
       ).fetchall()
       return [BookResponse(**dict(row)) for row in rows]


   def add_review(
       conn: sqlite3.Connection, book_id: int, review: ReviewCreate
   ) -> ReviewResponse | None:
       if get_book(conn, book_id) is None:
           return None
       cursor = conn.execute(
           "INSERT INTO reviews (book_id, rating, text, reviewer) VALUES (?, ?, ?, ?)",
           (book_id, review.rating, review.text, review.reviewer),
       )
       conn.commit()
       row = conn.execute("SELECT * FROM reviews WHERE id = ?", (cursor.lastrowid,)).fetchone()
       return ReviewResponse(**dict(row))


   def list_reviews(
       conn: sqlite3.Connection, book_id: int
   ) -> list[ReviewResponse] | None:
       if get_book(conn, book_id) is None:
           return None
       rows = conn.execute(
           "SELECT * FROM reviews WHERE book_id = ?", (book_id,)
       ).fetchall()
       return [ReviewResponse(**dict(row)) for row in rows]

The Updated Router — Pure HTTP Plumbing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The router becomes thin: obtain a connection, call a service function, handle HTTP
exceptions, return the response:

.. code-block:: python

   # routers/books.py — Ch2 version
   from bookshelf import services
   from bookshelf.database import get_connection

   @router.post("/", response_model=BookResponse, status_code=201)
   def create_book_endpoint(book: BookCreate) -> BookResponse:
       with get_connection() as conn:
           try:
               return services.create_book(conn, book)
           except Exception:
               raise HTTPException(status_code=409, detail="A book with this ISBN already exists")

   @router.get("/{book_id}", response_model=BookResponse)
   def get_book_endpoint(book_id: int) -> BookResponse:
       with get_connection() as conn:
           book = services.get_book(conn, book_id)
           if book is None:
               raise HTTPException(status_code=404, detail="Book not found")
           return book

The router handles only HTTP concerns: status codes, exception-to-HTTP-error translation,
and response serialization. The business logic lives in ``services.py``.

Update ``database.py`` to expose ``_create_schema`` for use in test fixtures:

.. code-block:: python

   # src/bookshelf/database.py
   def _create_schema(conn: sqlite3.Connection) -> None:
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


   def init_db() -> None:
       with get_connection() as conn:
           _create_schema(conn)

-----

**Exercise — Refactor to the Services Layer**

#. Create ``src/bookshelf/services.py`` with all the functions shown above.

#. Update ``src/bookshelf/database.py`` to expose ``_create_schema``.

#. Update both routers (``books.py`` and ``reviews.py``) to call ``services.*`` functions
   instead of executing SQL directly. The routers should contain no SQL — only calls to
   services and HTTPException raises.

#. Start the server and verify all existing endpoints still work:

   .. code-block:: bash

      $ uvicorn bookshelf.main:app --reload
      # Test via curl or the Swagger UI at http://localhost:8000/docs

#. Run the unit tests to confirm no regressions:

   .. code-block:: bash

      $ pytest tests/unit/ -v
      # All tests that were passing before should still pass

.. admonition:: Observation:

   After this refactor, the services layer has no dependency on FastAPI. ``services.py``
   imports only from the standard library (``sqlite3``) and from ``bookshelf.models``.
   This means you can test every service function as a plain Python function — no HTTP
   framework, no server, no ports. Chapter 3 will test the router layer via the HTTP
   interface, but it builds on this isolated, testable services layer.
