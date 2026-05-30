.. _ch02_tdd_cycle:

The TDD Cycle in Practice
==========================

Reading about TDD and doing TDD are different things. This section walks through two complete
Red → Green → Refactor cycles using real BookShelf API features. Follow along — run each
command at each step, observe the output, and build the muscle memory for the cycle.

-----

Cycle 1 — ``calculate_average_rating``
---------------------------------------

**Feature:** Given a list of integer ratings, calculate the average. Return ``None`` if there
are no ratings. This will be used to surface a book's average star rating.

Step 1 — Red
^^^^^^^^^^^^^

Before writing any implementation, write the tests. Create ``tests/unit/test_services.py``:

.. code-block:: python

   from bookshelf import services


   def test_average_rating_no_reviews():
       result = services.calculate_average_rating([])
       assert result is None


   def test_average_rating_single_review():
       result = services.calculate_average_rating([4])
       assert result == 4.0


   def test_average_rating_multiple_reviews():
       result = services.calculate_average_rating([5, 3, 4])
       assert result == 4.0

Run them. They must fail:

.. code-block:: bash

   $ pytest tests/unit/test_services.py -v
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf
   configfile: pyproject.toml
   collected 3 items

   tests/unit/test_services.py::test_average_rating_no_reviews FAILED      [ 33%]
   tests/unit/test_services.py::test_average_rating_single_review FAILED   [ 66%]
   tests/unit/test_services.py::test_average_rating_multiple_reviews FAILED [100%]

   ================================== FAILURES ===================================
   ______________ test_average_rating_no_reviews ______________

       from bookshelf import services

       def test_average_rating_no_reviews():
   >       result = services.calculate_average_rating([])
   E       AttributeError: module 'bookshelf.services' has no attribute 'calculate_average_rating'

   tests/unit/test_services.py:5: AttributeError
   =========================== short test summary info ============================
   FAILED tests/unit/test_services.py::test_average_rating_no_reviews
   FAILED tests/unit/test_services.py::test_average_rating_single_review
   FAILED tests/unit/test_services.py::test_average_rating_multiple_reviews
   ========================= 3 failed in 0.09s ====================================

The failure reason — ``AttributeError: module has no attribute 'calculate_average_rating'``
— confirms these are meaningful tests. They are not accidentally passing.

.. admonition:: Observation:

   The Red phase verifies that you have written a real test. If you run a test before writing
   the code and it *passes*, something is wrong — either the function already exists
   somewhere, or the test is not actually calling what you think it is. A test that cannot
   fail is not a test.

Step 2 — Green
^^^^^^^^^^^^^^

Write the minimum code to pass. Add to ``src/bookshelf/services.py``:

.. code-block:: python

   def calculate_average_rating(ratings: list[int]) -> float | None:
       if not ratings:
           return None
       return sum(ratings) / len(ratings)

Run the tests:

.. code-block:: bash

   $ pytest tests/unit/test_services.py -v
   ============================= test session starts ==============================
   collected 3 items

   tests/unit/test_services.py::test_average_rating_no_reviews PASSED      [ 33%]
   tests/unit/test_services.py::test_average_rating_single_review PASSED   [ 66%]
   tests/unit/test_services.py::test_average_rating_multiple_reviews PASSED [100%]

   ============================== 3 passed in 0.05s ====================================

All green.

Step 3 — Refactor
^^^^^^^^^^^^^^^^^

The implementation is already clean. But consider: what if ``ratings`` contains non-integer
values? Or very large lists? The current code handles both fine. No refactoring needed.

If the implementation had been more complex — say, a for-loop with manual accumulation —
the Refactor step is where you would replace it with the cleaner ``sum`` / ``len`` form,
running tests after each change to confirm nothing broke.

.. admonition:: Observation:

   "Refactor" does not mean "add features." It means improve the *structure* of the code
   without changing its behavior. Tests verify that behavior is preserved.

-----

Cycle 2 — ``search_books``
----------------------------

**Feature:** Search books by partial title or author match. The search should be
case-insensitive. Return an empty list when no results match.

.. admonition:: Crash Course: pytest Fixtures
   :class: dropdown

   A **fixture** is a function that pytest calls before a test to set up the resources
   that test needs — a database connection, a temporary file, a pre-populated table. The
   test declares what it needs by name in its parameter list; pytest wires everything up.

   **Why fixtures?** Without them, every test that needs a database would repeat the same
   setup code. Fixtures centralise that logic, keep tests short, and make teardown
   automatic.

   We will look at fixtures in depth in the next section. For now, just know that you can write a
   fixture that creates a temporary SQLite database, populates it with test data, and yields a connection to it — and then any test that needs a database can simply declare a parameter with the fixture's name.


Step 1 — Red
^^^^^^^^^^^^^

Add to ``tests/unit/test_services.py``. Notice that these tests need a real database
connection — add a minimal ``db_conn`` fixture for now (you will move it to ``conftest.py``
in the Fixtures section):

.. code-block:: python

   import sqlite3
   import pytest
   from bookshelf.database import _create_schema
   from bookshelf.models import BookCreate


   @pytest.fixture
   def db_conn(tmp_path):
       conn = sqlite3.connect(tmp_path / "test.db")
       conn.row_factory = sqlite3.Row
       conn.execute("PRAGMA foreign_keys = ON")
       _create_schema(conn)
       yield conn
       conn.close()


   @pytest.fixture
   def books_in_db(db_conn):
       for book in [
           BookCreate(title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008),
           BookCreate(title="The Pragmatic Programmer", author="David Thomas", isbn="9780135957059", year=1999),
           BookCreate(title="Design Patterns", author="Gang of Four", isbn="9780201633610", year=1994),
       ]:
           services.create_book(db_conn, book)
       return db_conn


   def test_search_books_by_title(books_in_db):
       results = services.search_books(books_in_db, "Clean")
       assert len(results) == 1
       assert results[0].title == "Clean Code"


   def test_search_books_by_author(books_in_db):
       results = services.search_books(books_in_db, "Martin")
       assert len(results) == 1
       assert results[0].author == "Robert Martin"


   def test_search_books_partial_match(books_in_db):
       results = services.search_books(books_in_db, "Prag")
       assert len(results) == 1
       assert results[0].title == "The Pragmatic Programmer"


   def test_search_books_no_results(books_in_db):
       results = services.search_books(books_in_db, "Kubernetes")
       assert results == []

Run them — they fail because ``services.search_books`` does not exist yet:

.. code-block:: bash

   $ pytest tests/unit/test_services.py -k "search" -v
   collected 4 items

   tests/unit/test_services.py::test_search_books_by_title FAILED          [ 25%]
   tests/unit/test_services.py::test_search_books_by_author FAILED         [ 50%]
   tests/unit/test_services.py::test_search_books_partial_match FAILED     [ 75%]
   tests/unit/test_services.py::test_search_books_no_results FAILED        [100%]

   ================================== FAILURES ===================================
   __________________ test_search_books_by_title __________________
       def test_search_books_by_title(books_in_db):
   >       results = services.search_books(books_in_db, "Clean")
   E       AttributeError: module 'bookshelf.services' has no attribute 'search_books'

   ========================= 4 failed in 0.11s ====================================

Step 2 — Green
^^^^^^^^^^^^^^

Add to ``src/bookshelf/services.py``:

.. code-block:: python

   import sqlite3
   from bookshelf.models import BookCreate, BookResponse


   def search_books(conn: sqlite3.Connection, query: str) -> list[BookResponse]:
       rows = conn.execute(
           "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
           (f"%{query}%", f"%{query}%"),
       ).fetchall()
       return [BookResponse(**dict(row)) for row in rows]

Also add ``create_book`` since the fixture uses it:

.. code-block:: python

   def create_book(conn: sqlite3.Connection, book: BookCreate) -> BookResponse:
       cursor = conn.execute(
           "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
           (book.title, book.author, book.isbn, book.year),
       )
       conn.commit()
       row = conn.execute("SELECT * FROM books WHERE id = ?", (cursor.lastrowid,)).fetchone()
       return BookResponse(**dict(row))

Run the tests:

.. code-block:: bash

   $ pytest tests/unit/test_services.py -k "search" -v
   collected 4 items

   tests/unit/test_services.py::test_search_books_by_title PASSED          [ 25%]
   tests/unit/test_services.py::test_search_books_by_author PASSED         [ 50%]
   tests/unit/test_services.py::test_search_books_partial_match PASSED     [ 75%]
   tests/unit/test_services.py::test_search_books_no_results PASSED        [100%]

   ============================== 4 passed in 0.10s ====================================

Step 3 — Refactor
^^^^^^^^^^^^^^^^^

SQLite's ``LIKE`` operator is case-insensitive for ASCII by default. The tests pass, but
confirm this explicitly with a test to document the behavior:

.. code-block:: python

   def test_search_books_case_insensitive(books_in_db):
       results = services.search_books(books_in_db, "clean")   # lowercase
       assert len(results) == 1
       assert results[0].title == "Clean Code"

Run all search tests — they all pass. The implementation is correct and the test suite now
explicitly documents the case-insensitivity guarantee.

.. code-block:: bash

   $ pytest tests/unit/test_services.py -k "search" -v
   collected 5 items

   tests/unit/test_services.py::test_search_books_by_title PASSED          [ 20%]
   tests/unit/test_services.py::test_search_books_by_author PASSED         [ 40%]
   tests/unit/test_services.py::test_search_books_partial_match PASSED     [ 60%]
   tests/unit/test_services.py::test_search_books_no_results PASSED        [ 80%]
   tests/unit/test_services.py::test_search_books_case_insensitive PASSED  [100%]

   ============================== 5 passed in 0.12s ====================================

-----

**Exercise — TDD for ``get_top_books``**

Use TDD to implement a new feature: a function that returns the top-rated books, ordered
by average rating descending.

**Specification:**
- ``services.get_top_books(conn, n: int) -> list[BookResponse]``
- Returns the top ``n`` books sorted by average rating (descending)
- Books with no reviews are sorted last (treat their average as 0)
- If ``n <= 0``, return an empty list
- If ``n`` exceeds the number of books, return all books (no error)

**Step 1 — Red.** Write at least these four tests (add them to ``test_services.py``):

.. code-block:: python

   def test_get_top_books_normal(populated_db):
       results = services.get_top_books(populated_db, 2)
       assert len(results) == 2
       # First result should have the highest average rating
       reviews_1 = services.list_reviews(populated_db, results[0].id)
       assert reviews_1 is not None

   def test_get_top_books_zero_n(populated_db):
       results = services.get_top_books(populated_db, 0)
       assert results == []

   def test_get_top_books_n_exceeds_total(populated_db):
       all_books = services.list_books(populated_db)
       results = services.get_top_books(populated_db, 999)
       assert len(results) == len(all_books)

   def test_get_top_books_no_reviews(db_conn, sample_book):
       services.create_book(db_conn, sample_book)
       results = services.get_top_books(db_conn, 1)
       assert len(results) == 1

Use the ``populated_db`` fixture from ``conftest.py`` (created in the Fixtures section). Run
the tests — confirm they all fail with ``AttributeError``.

**Step 2 — Green.** Implement ``services.get_top_books``. The SQL query needs a
``LEFT JOIN`` and ``GROUP BY`` to calculate averages:

.. code-block:: python

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

Run the tests — confirm all four pass.

**Step 3 — Refactor.** Add the router endpoint. In ``routers/books.py``, add:

.. code-block:: python

   @router.get("/top", response_model=list[BookResponse])
   def top_books(n: int = Query(default=5, ge=1, le=50)) -> list[BookResponse]:
       with get_connection() as conn:
           return services.get_top_books(conn, n)

Register this route before ``/{book_id}`` — for the same reason ``/search`` must come first.
Start the server and verify the endpoint works via ``curl`` or the Swagger UI.
