.. _ch03_regression_pipeline:

Building a Regression Pipeline
================================

.. admonition:: Crash Course: Make and Makefiles
   :class: dropdown

   Make is a build tool from 1976 that remains the most widely used command runner in
   software engineering. A ``Makefile`` defines named targets that run shell commands.

   **Basic structure:**

   .. code-block:: makefile

      target-name: prerequisite1 prerequisite2
      	command-to-run
      	another-command

   - The recipe (the commands) must be indented with a **tab**, not spaces.
   - A target with no prerequisites always runs.
   - A target with prerequisites only runs if the prerequisites are up to date.

   **Phony targets:** targets that are not file names. Declare them with ``.PHONY`` to
   prevent conflicts with files of the same name:

   .. code-block:: makefile

      .PHONY: test lint clean

      test:
      	pytest tests/ -v

      lint:
      	ruff check .

      clean:
      	rm -rf .pytest_cache htmlcov .coverage

   **Running targets:**

   .. code-block:: bash

      $ make test          # runs the test target
      $ make lint          # runs the lint target
      $ make               # runs the first target in the file (by convention, "all")

   **Chaining targets:** list prerequisites to build a pipeline:

   .. code-block:: makefile

      .PHONY: all lint test

      all: lint test
      	@echo "All checks passed!"

      lint:
      	ruff check .

      test:
      	pytest tests/ -v

   ``make all`` runs ``lint``, then ``test``. If ``lint`` fails, ``make`` stops — ``test``
   does not run. The ``@`` prefix suppresses command echo.

   For a deeper dive, see: `GNU Make manual <https://www.gnu.org/software/make/manual/make.html>`_

-----

What Is a Regression Pipeline?
--------------------------------

A regression pipeline is a single command that runs every quality check in sequence.
If the pipeline passes, the code is safe to merge or deploy. If it fails, you know
exactly which check caught the regression.

The pipeline enforces a discipline: no code reaches production unless it passes all
checks. This turns quality from an aspiration into a gate.

The value is not in any single check — it is in making them all run together,
automatically, with a single command.

-----

The Checks
-----------

For the BookShelf API, the pipeline runs four checks in order:

**1. Lint** — ``ruff check . && ruff format --check .``

Catches style violations, unused imports, and common bugs. Fast (under a second).
Fails fast before running expensive tests if there are obvious problems.

**2. Type check** — ``pyright src/``

Catches type errors: wrong argument types, missing return values, attribute errors on
typed objects. ``pyright`` is a fast, strict type checker. Runs in a few seconds.

**3. Unit tests** — ``pytest tests/unit/ -v``

Verifies all business logic in isolation. Fast (under a second for the BookShelf API).

**4. Integration tests with coverage** — ``pytest tests/integration/ tests/unit/ --cov --cov-report=term-missing``

Runs all tests and measures coverage. Slower than unit tests alone (involves TestClient
and SQLite I/O), but still fast enough for local development.

-----

The Makefile
-------------

.. code-block:: makefile

   .PHONY: lint typecheck test integration coverage check all

   lint:
   	ruff check .
   	ruff format --check .

   typecheck:
   	pyright src/

   test:
   	pytest tests/unit/ -v

   integration:
   	pytest tests/integration/ -v

   coverage:
   	pytest tests/ --cov --cov-report=term-missing

   check: lint typecheck
   	@echo "Static checks passed."

   all: lint typecheck test integration coverage
   	@echo ""
   	@echo "All checks passed. Ready to merge."

Save this as ``Makefile`` in the project root (next to ``pyproject.toml``).

.. admonition:: Observation:

   The ``check`` target runs only static analysis — no tests. Use it for a fast
   pre-commit check when you just want to verify code style and types. The ``all``
   target runs everything.

-----

Running the Pipeline
---------------------

First run, everything passes:

.. code-block:: bash

   $ make all
   ruff check .
   ruff format --check .
   pyright src/
   0 errors, 0 warnings, 0 informations
   pytest tests/unit/ -v
   ============================= test session starts ==============================
   collected 25 items

   tests/unit/test_isbn_service.py::test_validate_isbn_remote_found        PASSED
   tests/unit/test_isbn_service.py::test_validate_isbn_remote_not_found    PASSED
   tests/unit/test_isbn_service.py::test_validate_isbn_remote_timeout      PASSED
   tests/unit/test_mocking.py::test_add_review_book_not_found_skips_insert PASSED
   tests/unit/test_mocking.py::test_add_review_propagates_db_error         PASSED
   tests/unit/test_models.py::test_book_create_valid                       PASSED
   tests/unit/test_models.py::test_book_create_strips_isbn_hyphens         PASSED
   tests/unit/test_models.py::test_book_create_invalid_isbn_raises         PASSED
   tests/unit/test_services.py::test_average_rating_no_reviews             PASSED
   tests/unit/test_services.py::test_create_book_returns_response_with_id  PASSED
   ...
   ============================== 25 passed in 0.14s ==============================
   pytest tests/integration/ -v
   ============================= test session starts ==============================
   collected 15 items

   tests/integration/test_books_api.py::test_create_book_returns_201          PASSED
   tests/integration/test_books_api.py::test_get_book_returns_200             PASSED
   ...
   ============================== 15 passed in 0.48s ==============================
   pytest tests/ --cov --cov-report=term-missing
   ...
   TOTAL                               135      6    96%
   ============================== 40 passed in 0.63s ==============================

   All checks passed. Ready to merge.

-----

The Pipeline Catching a Regression
-------------------------------------

Now introduce a deliberate regression — change the expected status code for a successful
book creation from ``201`` to ``200`` in a test:

.. code-block:: python

   # Change this in tests/integration/test_books_api.py:
   assert response.status_code == 201   →   assert response.status_code == 200

Run the pipeline:

.. code-block:: bash

   $ make all
   ruff check .
   ruff format --check .
   pyright src/
   0 errors, 0 warnings, 0 informations
   pytest tests/unit/ -v
   ============================== 25 passed in 0.14s ==============================
   pytest tests/integration/ -v
   ============================= test session starts ==============================
   collected 15 items

   tests/integration/test_books_api.py::test_create_book_returns_201 FAILED  [  6%]

   ================================= FAILURES ====================================
   __________________ test_create_book_returns_201 ___________________

       def test_create_book_returns_201(client: TestClient) -> None:
           response = client.post("/books/", json={...})
   >       assert response.status_code == 200
   E       assert 201 == 200
   E        +  where 201 = <Response [201 Created]>.status_code

   tests/integration/test_books_api.py:9: AssertionError
   ============================== 1 failed in 0.21s ==============================
   make: *** [integration] Error 1

Make stops at the first failing target. The ``coverage`` target never runs — no point
measuring coverage of a broken test suite.

Restore the correct assertion and re-run. The pipeline passes.

-----

The Bridge to CI/CD
---------------------

This Makefile will become the foundation of the GitHub Actions pipeline in Chapter 5.
The CI configuration will run exactly these targets:

.. code-block:: yaml

   # .github/workflows/ci.yml (preview — full version in Ch5)
   jobs:
     quality:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: { python-version: "3.11" }
         - run: pip install -e ".[dev]"
         - run: make lint
         - run: make typecheck
         - run: make test
         - run: make integration
         - run: make coverage

The same command that catches regressions locally becomes the gate that prevents broken
code from merging to the main branch. The developer and CI use the same tool.

.. admonition:: Observation:

   One of the most common CI failures is "it passed on my machine." This happens when
   developers run tests differently locally than CI does. Running ``make all`` locally
   before pushing eliminates this class of problem — if the Makefile passes locally, it
   will pass in CI.

-----

**Exercises**

#. Create the ``Makefile`` in the project root with all six targets as shown above.
   Ensure the recipe lines are indented with a tab (not spaces). Run ``make all``:

   .. code-block:: bash

      $ make all

   Fix any failures until all checks pass.

#. Intentionally introduce a regression by changing a key assertion in one of the
   integration tests (for example, change ``assert response.status_code == 201`` to
   ``assert response.status_code == 200``).

   Run ``make all`` and observe:

   - Which target fails?
   - Does ``make`` run subsequent targets after the failure?
   - What does the error output tell you?

   Restore the correct assertion and run ``make all`` again to confirm it passes.

#. Add a ``clean`` target to the Makefile that removes the ``htmlcov/``, ```.coverage``,
   and ```.pytest_cache`` directories:

   .. code-block:: makefile

      clean:
      	rm -rf htmlcov .coverage .pytest_cache

   Verify it works:

   .. code-block:: bash

      $ make coverage     # generates htmlcov/
      $ ls htmlcov/       # directory exists
      $ make clean
      $ ls htmlcov/       # directory gone

#. **(Optional)** Add a ``help`` target that prints available commands. The ``@echo``
   lines suppress command echo; ``##`` comments on each target line can be parsed to
   generate self-documenting output. Research the pattern and implement it.
