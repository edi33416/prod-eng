.. _ch02_fixtures:

Fixtures and Test Data Management
===================================

Tests need setup: database connections, sample data, pre-populated tables. If you put this
setup code inside each test function, you repeat it dozens of times. When the setup logic
changes — and it will — you update dozens of places. Fixtures solve this by centralizing
test setup and making it composable.

-----

The Problem with Inline Setup
------------------------------

Without fixtures, a test suite looks like this:

.. code-block:: python

   def test_search_finds_book():
       conn = sqlite3.connect(":memory:")
       conn.row_factory = sqlite3.Row
       conn.execute("PRAGMA foreign_keys = ON")
       conn.execute("CREATE TABLE books ...")
       conn.execute("CREATE TABLE reviews ...")
       conn.execute("INSERT INTO books ...", ("Clean Code", "Robert Martin", ...))
       conn.commit()
       results = services.search_books(conn, "Clean")
       assert len(results) == 1
       conn.close()

   def test_get_book_exists():
       conn = sqlite3.connect(":memory:")   # identical setup repeated
       conn.row_factory = sqlite3.Row
       ...

Every test repeats the setup. If you change the schema, you update every test. This is
fragile and slow to maintain.

-----

``@pytest.fixture``
--------------------

A fixture is a function decorated with ``@pytest.fixture``. pytest injects it into any test
function that names it as a parameter:

.. code-block:: python

   import sqlite3
   import pytest
   from bookshelf.database import _create_schema


   @pytest.fixture
   def db_conn(tmp_path):
       conn = sqlite3.connect(tmp_path / "test.db")
       conn.row_factory = sqlite3.Row
       conn.execute("PRAGMA foreign_keys = ON")
       _create_schema(conn)
       yield conn              # test runs here
       conn.close()            # teardown runs after the test


   def test_search_finds_book(db_conn):   # ← fixture injected by name
       services.create_book(db_conn, BookCreate(
           title="Clean Code", author="Robert Martin",
           isbn="9780132350884", year=2008,
       ))
       results = services.search_books(db_conn, "Clean")
       assert len(results) == 1

pytest sees that ``test_search_finds_book`` has a parameter named ``db_conn``, finds the
matching fixture, calls it, and passes the result to the test. After the test finishes, the
code after ``yield`` runs as teardown.

Fixtures Are Composable
^^^^^^^^^^^^^^^^^^^^^^^^

Fixtures can depend on other fixtures. pytest builds the dependency graph and calls each
fixture exactly once per test (at the right scope):

.. code-block:: python

   @pytest.fixture
   def sample_book() -> BookCreate:
       return BookCreate(
           title="The Pragmatic Programmer",
           author="David Thomas",
           isbn="9780135957059",
           year=1999,
       )

   @pytest.fixture
   def book_in_db(db_conn, sample_book):   # depends on both db_conn and sample_book
       return services.create_book(db_conn, sample_book)

   def test_get_book_returns_correct_data(db_conn, book_in_db):
       result = services.get_book(db_conn, book_in_db.id)
       assert result is not None
       assert result.title == "The Pragmatic Programmer"

-----

``conftest.py`` — Shared Fixtures
-----------------------------------

Fixtures defined inside a test file are only available to tests in that file. Fixtures
defined in ``conftest.py`` are automatically available to all tests in the same directory
and subdirectories — no import needed.

Create ``tests/conftest.py``:

.. code-block:: python

   import sqlite3

   import pytest

   from bookshelf import services
   from bookshelf.database import _create_schema
   from bookshelf.models import BookCreate, ReviewCreate


   @pytest.fixture
   def db_conn(tmp_path):
       conn = sqlite3.connect(tmp_path / "test.db")
       conn.row_factory = sqlite3.Row
       conn.execute("PRAGMA foreign_keys = ON")
       _create_schema(conn)
       yield conn
       conn.close()


   @pytest.fixture
   def sample_book() -> BookCreate:
       return BookCreate(
           title="The Pragmatic Programmer",
           author="David Thomas",
           isbn="9780135957059",
           year=1999,
       )


   @pytest.fixture
   def sample_books() -> list[BookCreate]:
       return [
           BookCreate(title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008),
           BookCreate(title="Design Patterns", author="Gang of Four", isbn="9780201633610", year=1994),
           BookCreate(title="The Pragmatic Programmer", author="David Thomas", isbn="9780135957059", year=1999),
           BookCreate(title="Refactoring", author="Martin Fowler", isbn="9780201485677", year=1999),
           BookCreate(title="Working Effectively with Legacy Code", author="Michael Feathers", isbn="9780131177055", year=2004),
       ]


   @pytest.fixture
   def populated_db(db_conn, sample_books):
       for book in sample_books:
           services.create_book(db_conn, book)
       services.add_review(db_conn, 1, ReviewCreate(rating=5, text="Essential.", reviewer="alice"))
       services.add_review(db_conn, 1, ReviewCreate(rating=4, text="Very good.", reviewer="bob"))
       services.add_review(db_conn, 2, ReviewCreate(rating=3, text="Decent.", reviewer="alice"))
       services.add_review(db_conn, 3, ReviewCreate(rating=5, text="Classic.", reviewer="carol"))
       return db_conn

Now any test file under ``tests/`` can use ``db_conn``, ``sample_book``, ``sample_books``,
and ``populated_db`` without importing anything.

-----

Fixture Scopes
--------------

By default, a fixture runs fresh for every test (``scope="function"``). For expensive
setup — like building a large dataset or starting a server — you can share it across tests:

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Scope
     - Fixture is created
   * - ``function``
     - Once per test (default). Each test gets a clean instance.
   * - ``class``
     - Once per test class. All methods in the class share the instance.
   * - ``module``
     - Once per file. All tests in the file share the instance.
   * - ``session``
     - Once per pytest run. Shared across the entire test suite.

For database fixtures, ``function`` scope (the default) is almost always correct. A fresh
database per test means tests are isolated — one test's data cannot affect another's.

.. code-block:: python

   @pytest.fixture(scope="function")   # default — fresh db per test
   def db_conn(tmp_path):
       conn = sqlite3.connect(tmp_path / "test.db")
       _create_schema(conn)
       yield conn
       conn.close()

   @pytest.fixture(scope="session")    # created once for the entire run
   def http_client():
       client = httpx.Client(base_url="http://localhost:8000")
       yield client
       client.close()

.. admonition:: Observation:

   Use ``scope="session"`` only for truly expensive, read-only setup — like building a Docker
   container or loading a large ML model. Never use session scope for mutable state like a
   database connection. Two tests sharing the same database connection will interfere with
   each other in non-obvious ways.

-----

Built-in Fixtures
------------------

pytest provides several useful built-in fixtures:

``tmp_path``
  A ``pathlib.Path`` to a temporary directory that is unique per test and automatically
  cleaned up after the test run. Used above for the SQLite database file.

``capsys``
  Captures ``stdout`` and ``stderr`` output for assertions:

  .. code-block:: python

     def test_prints_greeting(capsys):
         print("Hello, world!")
         captured = capsys.readouterr()
         assert "Hello" in captured.out

``monkeypatch``
  Temporarily replaces attributes, environment variables, or functions. Useful for
  overriding configuration without modifying global state. You will use this in Chapter 3.

-----

Passing Arguments to Fixtures
-------------------------------

pytest fixtures do not accept arguments directly from the test — a test calls
``test_foo(db_conn)`` and pytest injects ``db_conn`` by name. But two patterns let you
vary what a fixture provides.

Factory Fixtures
^^^^^^^^^^^^^^^^^

The most common pattern: instead of returning a value, the fixture returns a *callable*.
The test calls the callable with whatever arguments it needs:

.. code-block:: python

   @pytest.fixture
   def make_book(db_conn):
       def _factory(title="Default Title", author="Default Author",
                    isbn="9780000000000", year=2000):
           book = BookCreate(title=title, author=author, isbn=isbn, year=year)
           return services.create_book(db_conn, book)
       return _factory


   def test_get_book_by_title(db_conn, make_book):
       make_book(title="Clean Code", isbn="9780132350884", year=2008)
       make_book(title="Refactoring", isbn="9780201485677", year=1999)

       results = services.search_books(db_conn, "Clean")
       assert len(results) == 1
       assert results[0].title == "Clean Code"

The fixture still manages teardown (``db_conn`` is closed after the test); the factory
only controls what gets inserted. Default argument values mean most tests only specify
what they care about.

Parametrized Fixtures
^^^^^^^^^^^^^^^^^^^^^^

Use ``params`` on the fixture decorator to run every test that uses the fixture once per
parameter value. pytest reports each combination as a separate test:

.. code-block:: python

   @pytest.fixture(params=["Clean", "Prag", "Design"])
   def search_query(request):
       return request.param   # request.param holds the current value


   def test_search_returns_results(populated_db, search_query):
       results = services.search_books(populated_db, search_query)
       assert len(results) >= 1

.. code-block:: bash

   $ pytest tests/unit/test_services.py::test_search_returns_results -v
   collected 3 items

   test_services.py::test_search_returns_results[Clean] PASSED
   test_services.py::test_search_returns_results[Prag] PASSED
   test_services.py::test_search_returns_results[Design] PASSED

``request`` is a built-in pytest fixture that provides metadata about the running test.
The only field you need here is ``request.param`` — the current item from the ``params``
list. Parametrized fixtures are most useful when the same fixture setup makes sense for
multiple configurations (different database states, different input files, different
environment settings).

.. admonition:: Observation:

   Use a **factory fixture** when different tests need different data — each test calls
   the factory with its own arguments to get exactly the state it needs.

   Use a **parametrized fixture** when you want to run the *same test* against multiple
   configurations — pytest generates a separate test case for each value automatically,
   without you writing the test more than once.

-----

**Exercise — Build the Shared Fixture Set**

#. Create ``tests/conftest.py`` with the four fixtures shown above: ``db_conn``,
   ``sample_book``, ``sample_books``, and ``populated_db``.

#. Remove any inline fixture definitions from ``tests/unit/test_services.py`` — the
   ``db_conn`` and ``books_in_db`` fixtures defined there in the TDD cycle section
   should now come from ``conftest.py``. Update references as needed.

#. Add a test that verifies ``populated_db`` has the expected data:

   .. code-block:: python

      def test_populated_db_has_five_books(populated_db):
          books = services.list_books(populated_db)
          assert len(books) == 5

      def test_populated_db_book_one_has_two_reviews(populated_db):
          reviews = services.list_reviews(populated_db, 1)
          assert reviews is not None
          assert len(reviews) == 2

   Run both — they should pass without any setup code in the test functions themselves.

#. Verify fixture isolation by running the full suite twice. The results must be identical —
   no test should depend on execution order or shared mutable state:

   .. code-block:: bash

      $ pytest tests/unit/ -v
      $ pytest tests/unit/ -v --randomly-seed=12345   # if pytest-randomly is installed

.. admonition:: Observation:

   ``tmp_path`` gives each test its own temporary directory. When your test creates
   ``tmp_path / "test.db"``, it gets a path like ``/tmp/pytest-42/test_search_finds_book0/test.db``
   — unique, isolated, and automatically deleted after the test run. This is why tests using
   ``db_conn`` are independent even though they all use SQLite.
