.. _ch02_parametrize:

Parametrized Tests and Markers
================================

Testing a function with multiple inputs is one of the most common testing patterns. The naive
approach — one test function per input — creates duplicate code and makes it easy to miss
edge cases. Parametrization collapses many test cases into a single declaration.

-----

``@pytest.mark.parametrize``
-----------------------------

The ``parametrize`` mark runs the same test body with a list of inputs. Each input set
becomes a separate test case — individually named, individually reported:

.. code-block:: python

   import pytest
   from bookshelf import services


   @pytest.mark.parametrize("isbn,expected", [
       ("9780132350884", True),   # valid 13-digit
       ("0132350882",   True),   # valid 10-digit
       ("123",          False),  # too short
       ("",             False),  # empty string
       ("97801323508841", False), # 14 digits — too long
       ("978013235088X", False),  # non-numeric character
   ])
   def test_validate_isbn(isbn: str, expected: bool):
       assert services.validate_isbn(isbn) == expected

Running this produces six individual test cases:

.. code-block:: bash

   $ pytest tests/unit/test_validation.py -v
   ============================= test session starts ==============================
   collected 6 items

   tests/unit/test_validation.py::test_validate_isbn[9780132350884-True]   PASSED [ 16%]
   tests/unit/test_validation.py::test_validate_isbn[0132350882-True]      PASSED [ 33%]
   tests/unit/test_validation.py::test_validate_isbn[123-False]            PASSED [ 50%]
   tests/unit/test_validation.py::test_validate_isbn[-False]               PASSED [ 66%]
   tests/unit/test_validation.py::test_validate_isbn[97801323508841-False] PASSED [ 83%]
   tests/unit/test_validation.py::test_validate_isbn[978013235088X-False]  PASSED [100%]

   ============================== 6 passed in 0.07s ====================================

If case 4 fails, you see exactly which input failed — not just "test_validate_isbn failed."

Adding a new edge case is a single line:

.. code-block:: python

   ("978-0-13-235088-4", True),   # hyphenated form — valid after stripping

Versus writing a new function:

.. code-block:: python

   # The verbose alternative nobody should write:
   def test_validate_isbn_hyphenated():
       assert services.validate_isbn("978-0-13-235088-4") is True

Parametrization also keeps your test matrix explicit. Reading the list of inputs immediately
shows which cases you have considered and which might be missing.

Readable Test IDs
^^^^^^^^^^^^^^^^^^

Use ``pytest.param`` with an ``id`` to give edge cases descriptive names:

.. code-block:: python

   @pytest.mark.parametrize("isbn,expected", [
       pytest.param("9780132350884",  True,  id="valid-13-digit"),
       pytest.param("0132350882",    True,  id="valid-10-digit"),
       pytest.param("123",           False, id="too-short"),
       pytest.param("",              False, id="empty"),
       pytest.param("97801323508841",False, id="too-long"),
   ])
   def test_validate_isbn(isbn: str, expected: bool):
       assert services.validate_isbn(isbn) == expected

Output now shows:

.. code-block:: text

   tests/unit/test_validation.py::test_validate_isbn[valid-13-digit] PASSED
   tests/unit/test_validation.py::test_validate_isbn[valid-10-digit] PASSED
   tests/unit/test_validation.py::test_validate_isbn[too-short]      PASSED
   ...

-----

Markers — Categorizing Tests
------------------------------

As a test suite grows, some tests are fast (milliseconds) and some are slow (seconds —
database round trips, file I/O). During active development, you want to run only the fast
tests. Markers let you categorize tests and filter them at run time.

**Define markers in ``pyproject.toml``** (avoids warnings about unknown marks):

.. code-block:: toml

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   markers = [
       "slow: marks tests as slow (deselect with '-m \"not slow\"')",
       "integration: marks integration tests (require external services)",
   ]
   addopts = "-v --tb=short"

**Apply markers to tests:**

.. code-block:: python

   @pytest.mark.slow
   def test_search_large_dataset(populated_db):
       # inserts 10,000 books — this takes a couple of seconds
       ...

   @pytest.mark.integration
   def test_api_create_book():
       # hits the real HTTP API
       ...

**Run only fast tests:**

.. code-block:: bash

   $ pytest -m "not slow"

**Run only integration tests:**

.. code-block:: bash

   $ pytest -m integration

**Run everything:**

.. code-block:: bash

   $ pytest   # no -m flag, all markers included

.. admonition:: Observation:

   In your CI pipeline (Chapter 5), you will run the full suite including slow and
   integration tests on every push. Locally, during a fast iteration loop, ``-m "not slow"``
   gives you sub-second feedback. Same test code, different invocation.

-----

``xfail`` and ``skip``
------------------------

``@pytest.mark.xfail`` marks a test as expected to fail — useful for documenting a known
bug while the fix is in progress:

.. code-block:: python

   @pytest.mark.xfail(reason="ISBN-10 checksum validation not yet implemented")
   def test_validate_isbn_checksum():
       # ISBNs are valid by digit count, but the check digit isn't validated yet
       assert services.validate_isbn("0000000000") is False   # fails — currently returns True

An ``xfail`` test that fails reports ``XFAIL`` (expected). If it accidentally passes, it
reports ``XPASS`` (unexpected pass) — which is also a signal to revisit the test.

``@pytest.mark.skip`` unconditionally skips a test:

.. code-block:: python

   @pytest.mark.skip(reason="test data not yet available")
   def test_import_from_goodreads():
       ...

Use ``skip`` and ``xfail`` sparingly. A skipped test provides zero value. Prefer
``xfail`` over ``skip`` for known bugs — it keeps the failing behavior visible and will
notify you when the bug is fixed.

-----

**Exercise — Parametrized ISBN and Year Validation**

#. Create ``tests/unit/test_validation.py``. Add ``validate_isbn`` to ``services.py``:

   .. code-block:: python

      def validate_isbn(isbn: str) -> bool:
          digits = isbn.replace("-", "").replace(" ", "")
          return len(digits) in (10, 13)

#. Write a parametrized test for ``validate_isbn`` with **at least 8 cases**, covering:

   - Valid 13-digit ISBN (numeric only)
   - Valid 10-digit ISBN
   - Valid 13-digit ISBN with hyphens (should normalize to valid)
   - ISBN that is too short
   - ISBN that is too long
   - Empty string
   - Non-numeric characters
   - All-zeros (structurally valid by length — checksum not enforced yet)

   Use ``pytest.param`` with descriptive ``id`` strings for each case.

#. Add a second parametrized test for year validation:

   .. code-block:: python

      @pytest.mark.parametrize("year,should_raise", [
          (1970, False),
          (2020, False),
          (1800, False),
          (2099, True),
          (3000, True),
      ])
      def test_year_validation(year: int, should_raise: bool):
          import datetime
          if should_raise:
              with pytest.raises(ValidationError):
                  BookCreate(title="X", author="Y", isbn="9780135957059", year=year)
          else:
              book = BookCreate(title="X", author="Y", isbn="9780135957059", year=year)
              assert book.year == year

#. Mark any test that uses ``populated_db`` with ``@pytest.mark.slow``. Run the suite
   with and without the marker:

   .. code-block:: bash

      $ pytest tests/unit/ -v              # all tests
      $ pytest tests/unit/ -v -m "not slow"  # fast tests only

   Confirm the ``populated_db`` tests are excluded in the second run.
