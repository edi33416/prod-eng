.. _ch02_test_organization:

Test Suite Organization
========================

A test suite is a codebase. It needs the same structural discipline as production code:
clear naming, logical grouping, shared configuration, and the ability to run subsets
quickly. A flat pile of test files named ``test1.py``, ``test2.py`` scales to about five
tests before it becomes unnavigable.

-----

Directory Structure
--------------------

By the end of this chapter, the test directory looks like this:

.. code-block:: text

   tests/
   ├── conftest.py              # shared fixtures (db_conn, sample_book, populated_db)
   ├── unit/
   │   ├── __init__.py
   │   ├── test_models.py       # Pydantic model validation tests
   │   ├── test_services.py     # business logic: CRUD, search, rating
   │   └── test_validation.py  # parametrized ISBN and year validation
   └── integration/             # populated in Chapter 3
       └── __init__.py

The separation between ``unit/`` and ``integration/`` is deliberate:

- **Unit tests** run in milliseconds. No external services. No network. No filesystem
  (except ``tmp_path``). They test one function at a time with injected dependencies.
- **Integration tests** run in seconds. They test the full HTTP stack with a real server
  and real database. They are slower and are run less frequently during development.

Chapter 3 populates ``integration/`` with tests that use FastAPI's ``TestClient`` to hit
real HTTP endpoints.

-----

Test Naming Conventions
------------------------

A test name should read like a specification. Use the pattern:
``test_<thing>_<scenario>_<expected_outcome>``:

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - Poor name
     - Good name
   * - ``test_search``
     - ``test_search_books_by_partial_title_returns_matches``
   * - ``test_create``
     - ``test_create_book_duplicate_isbn_raises_409``
   * - ``test_rating``
     - ``test_average_rating_no_reviews_returns_none``
   * - ``test_edge``
     - ``test_get_top_books_n_exceeds_total_returns_all``

The name is the documentation. When a test fails in CI, the name tells you immediately what
broke — without reading the test body:

.. code-block:: text

   FAILED tests/unit/test_services.py::test_create_book_duplicate_isbn_raises_409

vs:

.. code-block:: text

   FAILED tests/unit/test_services.py::test_create

-----

Running Subsets
----------------

.. code-block:: bash

   # All tests
   $ pytest

   # Specific directory
   $ pytest tests/unit/

   # Specific file
   $ pytest tests/unit/test_services.py

   # Specific test
   $ pytest tests/unit/test_services.py::test_average_rating_no_reviews

   # By name keyword (any test whose name contains "search")
   $ pytest -k "search"

   # By marker
   $ pytest -m "not slow"

   # Stop at first failure
   $ pytest -x

   # Verbose — show each test name
   $ pytest -v

   # Short tracebacks (good for large suites)
   $ pytest --tb=short

-----

Pytest Configuration in ``pyproject.toml``
--------------------------------------------

Centralizing pytest configuration in ``pyproject.toml`` ensures consistent behavior
across developer machines and CI:

.. code-block:: toml

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   markers = [
       "slow: marks tests as slow (deselect with '-m \"not slow\"')",
       "integration: marks integration tests (require external services)",
   ]
   addopts = "-v --tb=short --cov=bookshelf --cov-report=term-missing"

Key options:

- ``testpaths`` — where pytest looks for tests (avoids scanning ``src/``, ``venv/``, etc.)
- ``markers`` — declare custom markers to avoid ``PytestUnknownMarkWarning``
- ``addopts`` — flags applied to every run:
  - ``-v`` — verbose output
  - ``--tb=short`` — compact tracebacks
  - ``--cov=bookshelf`` — measure coverage of the ``bookshelf`` package
  - ``--cov-report=term-missing`` — print uncovered lines to the terminal

.. admonition:: Observation:

   ``addopts`` applies to *every* pytest invocation, including IDE test runners. If ``-v``
   makes output too noisy during quick local iterations, remove it from ``addopts`` and add
   it explicitly when needed. The ``--cov`` flags add a small overhead on every run — some
   teams move them to a separate ``Makefile`` target (``make test-coverage``) while the
   default ``pytest`` run stays fast.

-----

Reading Coverage Output
------------------------

After adding ``--cov=bookshelf --cov-report=term-missing``, every pytest run shows a
coverage table:

.. code-block:: bash

   $ pytest tests/unit/ -v
   ============================= test session starts ==============================
   ...
   ============================== 12 passed in 0.21s ==============================

   ---------- coverage: platform linux, python 3.11.9 ----------
   Name                              Stmts   Miss  Cover   Missing
   ---------------------------------------------------------------
   src/bookshelf/__init__.py             1      0   100%
   src/bookshelf/database.py            18      0   100%
   src/bookshelf/models.py              32      0   100%
   src/bookshelf/services.py            58      4    93%   87-90
   src/bookshelf/routers/books.py       42     42     0%   1-62
   src/bookshelf/routers/reviews.py     24     24     0%   1-36
   ---------------------------------------------------------------
   TOTAL                               175     70    60%

This tells you:

- ``services.py`` — 93% covered; lines 87–90 are not exercised by unit tests
- ``routers/books.py`` — 0% covered; routers are not tested at the unit level (they require
  the HTTP stack — Chapter 3 will cover these)

Coverage shows *what is not tested*, not *whether the tests are correct*. 100% coverage
does not mean the code is bug-free. It means every line ran during the test suite.

.. warning::

   Coverage metrics can be gamed. A test that calls every function but asserts nothing
   achieves 100% coverage while testing nothing. Use coverage to find *untested code paths*,
   not as a measure of test quality. Chapter 3 introduces a minimum coverage gate (e.g., 80%)
   that CI enforces — but it is a floor, not a target.

-----

**Exercise — Organize the Complete Test Suite**

#. Ensure the full directory structure is in place:

   .. code-block:: bash

      $ mkdir -p tests/unit tests/integration
      $ touch tests/__init__.py
      $ touch tests/unit/__init__.py
      $ touch tests/integration/__init__.py

#. Move or create all test files in the correct locations:

   - ``tests/conftest.py`` — shared fixtures from the Fixtures section
   - ``tests/unit/test_models.py`` — Pydantic model tests
   - ``tests/unit/test_services.py`` — service function tests
   - ``tests/unit/test_validation.py`` — parametrized validation tests

#. Update ``pyproject.toml`` with the configuration shown above (replace the existing
   ``[tool.pytest.ini_options]`` section).

#. Run the full suite with verbose output and check coverage:

   .. code-block:: bash

      $ pytest tests/unit/ -v

   Expected: all unit tests pass. ``services.py`` should be above 85% coverage.
   ``routers/`` will show 0% — that is correct for now.

#. Confirm you can run each subdirectory and individual file independently:

   .. code-block:: bash

      $ pytest tests/unit/test_validation.py -v
      $ pytest tests/unit/ -m "not slow" -v

#. Add a ``Makefile`` target for convenience (edit the project root ``Makefile`` — not the
   ``course-materials/`` build Makefile):

   .. code-block:: makefile

      .PHONY: test test-fast lint typecheck

      test:
      	pytest tests/

      test-fast:
      	pytest tests/unit/ -m "not slow"

      lint:
      	ruff check src/ && ruff format --check src/

      typecheck:
      	mypy src/

   Now ``make test-fast`` is the command for rapid feedback during development.
