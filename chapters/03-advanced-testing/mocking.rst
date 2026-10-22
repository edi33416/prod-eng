.. _ch03_mocking:

Mocking and Patching
=====================

.. admonition:: Crash Course: Python's ``unittest.mock`` Module
   :class: dropdown

   ``unittest.mock`` is Python's standard library for replacing real objects with
   controlled substitutes during tests. It ships with Python — no installation needed.

   **MagicMock** is the workhorse. It creates an object that accepts any attribute access
   or call without raising errors, recording everything it receives:

   .. code-block:: python

      from unittest.mock import MagicMock

      m = MagicMock()
      m.foo(1, 2)                      # call recorded
      m.bar.baz = "hello"              # attribute assignment recorded

      m.foo.assert_called_once_with(1, 2)   # passes
      m.foo.call_count                       # 1
      m.foo.return_value = 42                # future calls return 42

   **patch** replaces a named object in a module with a mock for the duration of a test:

   .. code-block:: python

      from unittest.mock import patch

      # As a decorator:
      @patch("mymodule.some_function")
      def test_something(mock_fn):
          mock_fn.return_value = 99
          result = code_that_calls_some_function()
          mock_fn.assert_called_once()

      # As a context manager:
      def test_something_else():
          with patch("mymodule.some_function") as mock_fn:
              mock_fn.return_value = 99
              result = code_that_calls_some_function()

   **side_effect** lets you simulate exceptions or return different values on successive calls:

   .. code-block:: python

      m = MagicMock()
      m.execute.side_effect = RuntimeError("connection reset")

      # Or a list — each call returns the next value:
      m.execute.side_effect = [first_result, second_result, RuntimeError("failed")]

   **Common mock assertions:**

   .. code-block:: python

      m.assert_called()                       # called at least once
      m.assert_called_once()                  # called exactly once
      m.assert_called_once_with(arg1, arg2)   # called once with these args
      m.assert_not_called()                   # never called
      assert m.call_count == 3                # called exactly 3 times

   **The key rule:** ``patch("a.b.c")`` patches the name ``c`` *in module ``a.b``*, not
   where ``c`` was originally defined. Patch where it is used, not where it is defined.

   For a deeper dive, see: `unittest.mock documentation <https://docs.python.org/3/library/unittest.mock.html>`_

-----

Why Mock?
----------

Three reasons to replace a real dependency with a mock:

**It is slow.** A real database connection involves file I/O and potentially network
latency. A mock that returns pre-set data is instantaneous. For a unit test that runs
hundreds of times per day, the difference matters.

**It is external.** An external HTTP API may be unavailable in your test environment,
may have rate limits, or may return inconsistent data. A mock returns exactly what you
tell it to return, every time.

**It is non-deterministic.** Functions that return the current time, a random number,
or a UUID return different values on every call. To assert that your code behaves
correctly given a specific time or UUID, you need control over what those functions
return.

When none of these conditions apply — when the dependency is fast, local, and
deterministic — prefer using the real thing. Over-mocking creates tests that pass
against an implementation that does not match reality.

.. admonition:: Observation:

   The most common over-mocking mistake is mocking your own code. If you mock
   ``services.create_book`` in a test of ``services.create_book``, you are not testing
   anything — the test will pass regardless of what the function actually does. Mock
   external systems (databases, HTTP clients, file I/O, clocks), not internal logic.

-----

Patching a Dependency
----------------------

The ``add_review`` function in ``services.py`` first checks whether the book exists,
then inserts the review:

.. code-block:: python

   def add_review(conn, book_id, review):
       if get_book(conn, book_id) is None:
           return None
       cursor = conn.execute(
           "INSERT INTO reviews (book_id, rating, text, reviewer) VALUES (?, ?, ?, ?)",
           (book_id, review.rating, review.text, review.reviewer),
       )
       conn.commit()
       ...

Suppose you want to test the branch where the book does not exist — without setting up
a real database at all. Patch ``get_book`` to return ``None``:

.. code-block:: python

   from unittest.mock import MagicMock, patch

   from bookshelf import services
   from bookshelf.models import ReviewCreate


   def test_add_review_book_not_found_skips_insert():
       mock_conn = MagicMock()
       review = ReviewCreate(rating=4, text="Good book.", reviewer="alice")

       with patch("bookshelf.services.get_book", return_value=None):
           result = services.add_review(mock_conn, 999, review)

       assert result is None
       mock_conn.execute.assert_not_called()

Run it:

.. code-block:: bash

   $ pytest tests/unit/test_mocking.py::test_add_review_book_not_found_skips_insert -v
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf-ch3
   configfile: pyproject.toml
   collected 1 item

   tests/unit/test_mocking.py::test_add_review_book_not_found_skips_insert PASSED [ 100%]

   ============================== 1 passed in 0.04s ==============================

The test verifies two things: the function returns ``None`` (correct return value), and
no INSERT was attempted (correct behavior — no DB write when book is absent). The
``mock_conn.execute.assert_not_called()`` assertion would fail if someone accidentally
removed the early-exit guard.

.. admonition:: Observation:

   ``patch("bookshelf.services.get_book", ...)`` patches the name ``get_book`` as it
   exists *inside* the ``bookshelf.services`` module. This works because ``add_review``
   calls ``get_book`` by looking it up in its own module's namespace. If the function
   called ``bookshelf.services.get_book`` explicitly (using the full path), the patch
   target would need to match.

-----

The ``@patch`` Decorator
-------------------------

The context manager works well inside a test function. For class-based tests or when the
mock needs to persist through the entire test, use the ``@patch`` decorator. The mock
object is passed as an extra argument:

.. code-block:: python

   from unittest.mock import patch, MagicMock
   import pytest

   from bookshelf import services
   from bookshelf.models import BookResponse, ReviewCreate


   @patch("bookshelf.services.get_book")
   def test_add_review_calls_get_book_with_correct_id(mock_get_book):
       mock_get_book.return_value = BookResponse(
           id=1, title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
       )
       mock_conn = MagicMock()
       mock_conn.execute.return_value.lastrowid = 42
       mock_conn.execute.return_value.fetchone.return_value = {
           "id": 42, "book_id": 1, "rating": 5, "text": "Great.", "reviewer": "alice"
       }

       services.add_review(mock_conn, 1, ReviewCreate(rating=5, text="Great.", reviewer="alice"))

       mock_get_book.assert_called_once_with(mock_conn, 1)

The decorator is syntactic sugar for the context manager. When multiple patches are
needed, stack them — the innermost decorator maps to the first extra argument:

.. code-block:: python

   @patch("bookshelf.services.get_book")
   @patch("bookshelf.services.validate_isbn")
   def test_with_two_patches(mock_validate, mock_get_book):
       # mock_validate → patch("validate_isbn") — innermost
       # mock_get_book → patch("get_book") — outermost
       ...

-----

Simulating Failures with ``side_effect``
-----------------------------------------

To test how your code handles a failing dependency, assign ``side_effect`` to an
exception class or instance:

.. code-block:: python

   import sqlite3
   from unittest.mock import MagicMock, patch
   import pytest

   from bookshelf import services
   from bookshelf.models import BookResponse, ReviewCreate


   def test_add_review_propagates_db_error():
       mock_conn = MagicMock()
       mock_book = BookResponse(
           id=1, title="Clean Code", author="Robert Martin", isbn="9780132350884", year=2008
       )
       review = ReviewCreate(rating=5, text="Essential.", reviewer="alice")

       with patch("bookshelf.services.get_book", return_value=mock_book):
           mock_conn.execute.side_effect = sqlite3.OperationalError("database is locked")

           with pytest.raises(sqlite3.OperationalError, match="database is locked"):
               services.add_review(mock_conn, 1, review)

.. code-block:: bash

   $ pytest tests/unit/test_mocking.py::test_add_review_propagates_db_error -v
   ============================= test session starts ==============================
   collected 1 item

   tests/unit/test_mocking.py::test_add_review_propagates_db_error PASSED [ 100%]

   ============================== 1 passed in 0.03s ==============================

This test verifies that ``add_review`` does not silently swallow database errors. If a
future developer wraps the execute call in a bare ``except Exception: return None``,
this test will fail — catching what should be a fatal error.

-----

Mocking External HTTP Calls
-----------------------------

The BookShelf API includes an ``isbn_service`` module that validates ISBNs against
Open Library's public API:

.. code-block:: python

   # bookshelf/isbn_service.py
   import httpx

   _OPENLIBRARY_URL = "https://openlibrary.org/api/books"


   def validate_isbn_remote(isbn: str) -> bool:
       """Returns True if the ISBN exists in Open Library."""
       response = httpx.get(
           _OPENLIBRARY_URL,
           params={"bibkeys": f"ISBN:{isbn}", "format": "json"},
           timeout=5.0,
       )
       response.raise_for_status()
       return bool(response.json())

This function makes a real HTTP call. In a unit test, that call is slow, requires a
network connection, and depends on a third-party service. Mock it:

.. code-block:: python

   # tests/unit/test_isbn_service.py
   from unittest.mock import MagicMock, patch
   import httpx
   import pytest

   from bookshelf.isbn_service import validate_isbn_remote


   def test_validate_isbn_remote_found():
       mock_response = MagicMock()
       mock_response.json.return_value = {"ISBN:9780135957059": {"title": "The Pragmatic Programmer"}}
       mock_response.raise_for_status.return_value = None

       with patch("bookshelf.isbn_service.httpx.get", return_value=mock_response):
           result = validate_isbn_remote("9780135957059")

       assert result is True


   def test_validate_isbn_remote_not_found():
       mock_response = MagicMock()
       mock_response.json.return_value = {}   # Open Library returns empty dict for unknown ISBN
       mock_response.raise_for_status.return_value = None

       with patch("bookshelf.isbn_service.httpx.get", return_value=mock_response):
           result = validate_isbn_remote("9780000000000")

       assert result is False


   def test_validate_isbn_remote_timeout():
       with patch(
           "bookshelf.isbn_service.httpx.get",
           side_effect=httpx.TimeoutException("timed out"),
       ):
           with pytest.raises(httpx.TimeoutException):
               validate_isbn_remote("9780135957059")

.. code-block:: bash

   $ pytest tests/unit/test_isbn_service.py -v
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf-ch3
   configfile: pyproject.toml
   collected 3 items

   tests/unit/test_isbn_service.py::test_validate_isbn_remote_found     PASSED [ 33%]
   tests/unit/test_isbn_service.py::test_validate_isbn_remote_not_found PASSED [ 66%]
   tests/unit/test_isbn_service.py::test_validate_isbn_remote_timeout   PASSED [100%]

   ============================== 3 passed in 0.07s ==============================

Three tests, each covering a different code path, zero real network calls. The tests
run in milliseconds and produce the same result every time.

.. admonition:: Observation:

   The target for patching ``httpx.get`` is ``bookshelf.isbn_service.httpx.get`` — not
   ``httpx.get``. The ``isbn_service`` module imports ``httpx`` and then calls
   ``httpx.get``. Patching ``bookshelf.isbn_service.httpx`` replaces the ``httpx``
   name inside ``isbn_service``'s namespace. Patching ``httpx.get`` directly would patch
   the original location and leave ``isbn_service``'s import unaffected.

-----

When NOT to Mock
-----------------

Mocking is a tool for managing dependencies you cannot control. It becomes harmful when
overused:

- **Don't mock your own service functions in unit tests of those functions.** A test of
  ``create_book`` that mocks ``create_book`` is circular and meaningless.

- **Don't mock SQLite.** SQLite is fast, deterministic, and available everywhere. Using a
  real SQLite connection in unit tests (as Ch2 does) is cheaper and more correct than
  a mock. Reserve database mocking for when the DB is slow (Postgres with remote network
  latency) or when you are explicitly testing error-handling paths.

- **Don't mock deeply.** If you need to mock five layers of internal calls to test one
  function, the function is doing too much. Refactor first, then test.

- **Don't mock to avoid writing fixtures.** A ``MagicMock()`` that returns the right data
  for one test will silently return wrong data for the next. A real fixture is more
  reliable and easier to understand.

The rule of thumb: mock external systems at their boundaries. Test internal code with
real inputs and real objects.

-----

**Exercises**

#. Write a test ``test_add_review_db_insert_fails`` in ``tests/unit/test_mocking.py``.
   The test should:

   - Use ``patch("bookshelf.services.get_book", return_value=<a valid BookResponse>)``
     to bypass the existence check.
   - Assign ``side_effect=Exception("constraint violation")`` to ``mock_conn.execute``
     to simulate the INSERT failing.
   - Assert that the exception propagates (the service function does not swallow it).

   Run the test. It should pass.

#. Write tests for ``validate_isbn_remote`` in ``tests/unit/test_isbn_service.py``:

   - ``test_validate_isbn_remote_http_error`` — simulate ``raise_for_status`` raising
     ``httpx.HTTPStatusError``. Assert the exception propagates.
   - ``test_validate_isbn_remote_calls_correct_url`` — assert that ``httpx.get`` was
     called with ``_OPENLIBRARY_URL`` and the correct ``params`` for a given ISBN.
     Use ``mock_get.assert_called_once_with(...)`` to verify the arguments.

   Run both tests. Both should pass.
