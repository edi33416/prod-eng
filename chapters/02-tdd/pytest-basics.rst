.. _ch02_pytest_basics:

pytest Fundamentals
====================

pytest is the standard Python testing framework. It is simple to start with — a test is just
a function — and powerful enough for the most complex test suites. This section covers the
mechanics: writing tests, running them, and reading their output.

.. admonition:: Crash Course: Python's assert Statement
   :class: dropdown

   ``assert`` evaluates an expression and raises ``AssertionError`` if it is falsy.
   It is how you express expected behavior in a test.

   **Basic usage:**

   .. code-block:: python

      assert 1 + 1 == 2            # passes silently
      assert "foo" in "foobar"     # passes silently
      assert [] == []               # passes silently

      assert 1 + 1 == 3            # raises AssertionError

   **With a message:**

   .. code-block:: python

      assert result == 5, f"Expected 5, got {result}"

   **Common patterns:**

   .. code-block:: python

      assert x == y                # equality
      assert x != y                # inequality
      assert x is None             # identity check (not ==)
      assert x is not None
      assert isinstance(x, int)    # type check
      assert "foo" in collection   # membership

   **Asserting exceptions with pytest:**

   .. code-block:: python

      import pytest

      def test_division_by_zero():
          with pytest.raises(ZeroDivisionError):
              _ = 1 / 0

      # Capture the exception to inspect it:
      def test_invalid_isbn_raises():
          with pytest.raises(ValueError) as exc_info:
              BookCreate(title="X", author="Y", isbn="bad", year=2020)
          assert "ISBN" in str(exc_info.value)

   For a deeper dive, see: `pytest assertion documentation <https://docs.pytest.org/en/stable/how-to/assert.html>`_

-----

Test Discovery
--------------

pytest finds tests automatically by scanning for:

- Files matching ``test_*.py`` or ``*_test.py``
- Functions inside those files named ``test_*``
- Classes named ``Test*`` (no ``__init__`` needed)

.. code-block:: text

   tests/
     unit/
       test_models.py       ← discovered
       test_services.py     ← discovered
       helpers.py           ← NOT discovered (no test_ prefix)

You do not need to register tests anywhere. Drop a ``test_*.py`` file in the right place and
pytest finds it.

-----

Your First Tests
-----------------

Create ``tests/unit/test_models.py``:

.. code-block:: python

   import pytest
   from pydantic import ValidationError

   from bookshelf.models import BookCreate, ReviewCreate


   def test_book_create_valid():
       book = BookCreate(
           title="The Pragmatic Programmer",
           author="David Thomas",
           isbn="9780135957059",
           year=1999,
       )
       assert book.title == "The Pragmatic Programmer"
       assert book.isbn == "9780135957059"
       assert book.year == 1999


   def test_book_create_strips_isbn_hyphens():
       book = BookCreate(
           title="Clean Code",
           author="Robert Martin",
           isbn="978-0-13-235088-4",  # hyphenated form
           year=2008,
       )
       assert book.isbn == "9780132350884"  # hyphens removed by validator


   def test_book_create_invalid_isbn_raises():
       with pytest.raises(ValidationError) as exc_info:
           BookCreate(title="X", author="Y", isbn="123", year=2020)
       assert "ISBN" in str(exc_info.value)

-----

Running Tests
--------------

From the project root (with the virtual environment active):

.. code-block:: bash

   $ pytest
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf
   configfile: pyproject.toml
   collected 3 items

   tests/unit/test_models.py ...                                            [100%]

   ============================== 3 passed in 0.12s ==============================

**Useful flags:**

.. code-block:: bash

   $ pytest -v                           # verbose — shows each test name
   $ pytest -v tests/unit/test_models.py # specific file
   $ pytest -k "test_isbn"               # tests whose name contains "isbn"
   $ pytest --tb=short                   # shorter traceback on failures
   $ pytest -x                           # stop after first failure

Verbose output:

.. code-block:: bash

   $ pytest -v tests/unit/test_models.py
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf
   configfile: pyproject.toml
   collected 3 items

   tests/unit/test_models.py::test_book_create_valid PASSED                 [ 33%]
   tests/unit/test_models.py::test_book_create_strips_isbn_hyphens PASSED   [ 66%]
   tests/unit/test_models.py::test_book_create_invalid_isbn_raises PASSED   [100%]

   ============================== 3 passed in 0.12s ==============================

-----

Assertion Introspection — Reading Failure Output
-------------------------------------------------

When an assertion fails, pytest does not just say "assertion failed." It shows you the full
values that were compared. This is one of pytest's most useful features.

Consider a test with a wrong expected value:

.. code-block:: python

   def test_book_year_wrong_expected():
       book = BookCreate(title="X", author="Y", isbn="9780135957059", year=1999)
       assert book.year == 2000   # wrong expected value

.. code-block:: bash

   $ pytest tests/unit/test_models.py::test_book_year_wrong_expected -v
   ============================= test session starts ==============================
   collected 1 item

   tests/unit/test_models.py::test_book_year_wrong_expected FAILED          [100%]

   ================================== FAILURES ===================================
   __________________ test_book_year_wrong_expected __________________

       def test_book_year_wrong_expected():
           book = BookCreate(title="X", author="Y", isbn="9780135957059", year=1999)
   >       assert book.year == 2000
   E       assert 1999 == 2000
   E        +  where 1999 = BookCreate(title='X', author='Y', isbn='9780135957059', year=1999).year

   tests/unit/test_models.py:5: AssertionError
   ========================= 1 failed in 0.13s ================================

pytest prints:
- The exact line that failed (``>``)
- The left and right values of the assertion (``E assert 1999 == 2000``)
- Where the left value came from (``+  where 1999 = ...``)

No print debugging required. Read the failure output and you know exactly what happened.

-----

**Exercise — First Unit Tests for BookShelf Models**

#. Ensure the test directory structure exists and the package is installed:

   .. code-block:: bash

      $ mkdir -p tests/unit
      $ touch tests/__init__.py tests/unit/__init__.py
      $ pip install -e ".[dev]"

#. Create ``tests/unit/test_models.py`` with the three tests shown above (``test_book_create_valid``,
   ``test_book_create_strips_isbn_hyphens``, ``test_book_create_invalid_isbn_raises``).

#. Run them — all three should pass:

   .. code-block:: bash

      $ pytest tests/unit/test_models.py -v

#. Add two more tests for the year validator and the review rating constraint:

   - ``test_book_create_future_year_raises`` — create a ``BookCreate`` with ``year=2099``,
     assert ``ValidationError`` is raised and the message mentions "future"
   - ``test_review_create_rating_out_of_range_raises`` — create a ``ReviewCreate`` with
     ``rating=6``, assert ``ValidationError`` is raised

   Run the full file. All 5 tests should pass.

#. Intentionally break one assertion (e.g., change ``assert book.year == 1999`` to
   ``assert book.year == 2000``) and re-run. Read the failure output carefully —
   identify which values pytest compared and how it determined they didn't match.
   Restore the correct assertion.
