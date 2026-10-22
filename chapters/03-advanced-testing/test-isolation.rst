.. _ch03_test_isolation:

Test Isolation and Fixture Factories
======================================

The Order-Dependent Test Suite
--------------------------------

Consider a test file where Test A creates a book and Test B assumes that book exists.
If you run them in order — A then B — both pass. If you run only B, it fails.
If the test runner changes order, B fails.

Tests with hidden dependencies on shared state are called *order-dependent* or *flaky*
tests. They are worse than no tests: they pass on some machines and fail on others, pass
locally and fail in CI, and fail after a seemingly unrelated change. Teams stop trusting
the suite.

This is common in early test suites. The first few tests are simple and pass easily.
Then a developer writes a test that depends on data from an earlier test — not
intentionally, but because the database state from the earlier test happened to be there
when they wrote the new test. The test suite becomes brittle.

-----

The Problem: Shared Database State
-------------------------------------

The root cause is shared state. If multiple tests write to the same database and that
state persists between tests, tests become coupled.

The Ch2 unit tests avoid this because they use the ``db_conn`` fixture, which creates a
fresh SQLite file in a unique ``tmp_path`` directory for each test. Each test starts
with an empty database.

The integration tests use the ``client`` fixture, which patches ``DB_PATH`` to a new
temp path per test. Each test has its own clean database.

But consider what happens if these fixtures have the wrong scope — or if a developer
reuses a module-level connection:

.. code-block:: python

   # Bad: module-level connection — state persists across all tests in the file
   conn = create_test_connection()

   def test_create_book():
       services.create_book(conn, sample_book)   # inserts id=1

   def test_list_books():
       books = services.list_books(conn)
       assert len(books) == 1   # only passes if test_create_book ran first

The fix is always the same: give each test its own database, created fresh and cleaned up
after.

-----

Fixture Scope
--------------

pytest fixtures have a ``scope`` parameter that controls how often the fixture is
created and destroyed:

.. code-block:: python

   @pytest.fixture(scope="function")   # default — new instance per test function
   @pytest.fixture(scope="module")     # one instance per test module (file)
   @pytest.fixture(scope="session")    # one instance for the entire test run

The default scope (``"function"``) is the safest. Use ``"module"`` or ``"session"``
only for expensive read-only fixtures (like loading a large dataset from disk once).

**The rule:** any fixture that writes to a database or modifies shared state must use
``scope="function"`` (the default). Otherwise tests will interfere with each other.

The ``db_conn`` and ``client`` fixtures from Ch2 and this chapter are both
``scope="function"`` by default. This is correct.

-----

Fixture Factories
------------------

Tests that create data before exercising behavior often repeat the same creation code:

.. code-block:: python

   def test_search_returns_matching_books(db_conn):
       services.create_book(db_conn, BookCreate(title="Clean Code", author="Robert Martin",
                                                isbn="9780132350884", year=2008))
       services.create_book(db_conn, BookCreate(title="The Pragmatic Programmer",
                                                author="David Thomas", isbn="9780135957059",
                                                year=1999))
       results = services.search_books(db_conn, "Pragmatic")
       assert len(results) == 1

   def test_top_books_orders_by_rating(db_conn):
       services.create_book(db_conn, BookCreate(title="Clean Code", author="Robert Martin",
                                                isbn="9780132350884", year=2008))
       services.create_book(db_conn, BookCreate(title="The Pragmatic Programmer",
                                                author="David Thomas", isbn="9780135957059",
                                                year=1999))
       # ... more setup ...

This repetition has a real cost: when the ``BookCreate`` model changes (a new required
field, say), every test that constructs one must be updated. The construction code is
also noisy — it obscures what the test is actually verifying.

A **fixture factory** is a fixture that returns a function, which creates test objects
with sensible defaults and accepts overrides:

.. code-block:: python

   # tests/conftest.py (add to the existing conftest)
   @pytest.fixture
   def book_factory(db_conn):
       def _create(**overrides: object) -> BookResponse:
           defaults = {
               "title": "Test Book",
               "author": "Test Author",
               "isbn": "9780000000000",
               "year": 2020,
           }
           defaults.update(overrides)
           return services.create_book(db_conn, BookCreate(**defaults))
       return _create


   @pytest.fixture
   def review_factory(db_conn):
       def _create(book_id: int, **overrides: object) -> ReviewResponse:
           defaults = {
               "rating": 5,
               "text": "Great book.",
               "reviewer": "test_user",
           }
           defaults.update(overrides)
           return services.add_review(db_conn, book_id, ReviewCreate(**defaults))
       return _review_factory

The refactored tests become dramatically shorter and focused on what they actually test:

.. code-block:: python

   def test_search_returns_matching_books(book_factory):
       book_factory(title="Clean Code")
       book_factory(title="The Pragmatic Programmer")

       results = services.search_books(db_conn, "Pragmatic")
       assert len(results) == 1


   def test_top_books_first_place(db_conn, book_factory, review_factory):
       book1 = book_factory(title="High Rated", isbn="9781000000001")
       book2 = book_factory(title="Low Rated", isbn="9781000000002")

       review_factory(book1.id, rating=5)
       review_factory(book1.id, rating=5)
       review_factory(book2.id, rating=2)

       top = services.get_top_books(db_conn, 1)
       assert top[0].title == "High Rated"

.. admonition:: Observation:

   A factory fixture has a subtle difference from a data fixture. The ``sample_books``
   fixture from Ch2 returns a list of ``BookCreate`` objects — the data itself. A factory
   returns a callable that creates and persists data. Use data fixtures for read-only
   configuration; use factories when tests need to create records with controlled variation.

-----

Unique ISBN Generation
-----------------------

A factory that always creates the same ISBN will fail on the second call — the database
enforces ISBN uniqueness. The factory must generate unique ISBNs:

.. code-block:: python

   import itertools

   @pytest.fixture
   def book_factory(db_conn):
       counter = itertools.count(1)

       def _create(**overrides: object) -> BookResponse:
           defaults = {
               "title": "Test Book",
               "author": "Test Author",
               "isbn": f"978{next(counter):010d}",   # e.g. "9780000000001"
               "year": 2020,
           }
           defaults.update(overrides)
           return services.create_book(db_conn, BookCreate(**defaults))

       return _create

Now each call to ``book_factory()`` generates a different ISBN. Tests that explicitly
need a specific ISBN can still pass it as an override:
``book_factory(isbn="9780135957059")``.

-----

Integration Test Factories
----------------------------

The same pattern works for integration tests that drive the API via HTTP. The factory
calls the ``client`` instead of the service directly:

.. code-block:: python

   # tests/integration/conftest.py (add to the existing conftest)
   import itertools

   @pytest.fixture
   def create_book(client):
       counter = itertools.count(1)

       def _create(**overrides):
           defaults = {
               "title": "Test Book",
               "author": "Test Author",
               "isbn": f"978{next(counter):010d}",
               "year": 2020,
           }
           defaults.update(overrides)
           response = client.post("/books/", json=defaults)
           assert response.status_code == 201, response.json()
           return response.json()

       return _create

Tests using this fixture are clean and readable:

.. code-block:: python

   def test_delete_book(client, create_book):
       book = create_book(title="To Delete")
       response = client.delete(f"/books/{book['id']}")
       assert response.status_code == 204

       response = client.get(f"/books/{book['id']}")
       assert response.status_code == 404

-----

**Exercises**

#. Add the ``book_factory`` and ``review_factory`` fixtures to ``tests/conftest.py``
   using the counter-based ISBN generation shown above.

   Note: the ``review_factory`` fixture shown earlier has a typo — ``return
   _review_factory`` should be ``return _create``. Fix it before using it.

#. Refactor at least five tests in ``tests/unit/test_services.py`` to use
   ``book_factory`` and ``review_factory`` instead of manually constructing
   ``BookCreate`` objects. For each refactored test, verify:

   - The test still passes.
   - The test body is shorter and focuses on the behavior being tested.
   - The construction boilerplate is gone.

#. Add the ``create_book`` factory fixture to ``tests/integration/conftest.py``.
   Refactor the integration tests that construct book data inline to use it instead.
   Run ``pytest tests/integration/ -v`` to verify all tests still pass.
