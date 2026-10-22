.. _ch03_coverage:

Test Coverage
==============

The Confidence Trap
--------------------

A team ships a new feature. Every test passes. Coverage is 94%. Two hours after deploy,
the feature is returning wrong results for a specific input range.

The investigation reveals the gap: the business rule that handles amounts over $10,000
was implemented, was executed by one test, and that test asserted on the response status
code — not on the calculated value. The line was covered. The logic was wrong.

Coverage is a useful metric. It is not a correctness guarantee.

Understanding what coverage measures — and what it does not — prevents this kind of
misplaced confidence.

-----

What Coverage Measures
-----------------------

Coverage tracks which lines of source code are executed during a test run. A line is
"covered" if at least one test caused it to execute.

``pytest-cov`` is the standard coverage tool for pytest:

.. code-block:: bash

   $ pip install pytest-cov

Run tests with coverage:

.. code-block:: bash

   $ pytest --cov=bookshelf --cov-report=term-missing tests/
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf-ch3
   configfile: pyproject.toml
   collected 34 items

   tests/unit/test_isbn_service.py ...                                      [  8%]
   tests/unit/test_mocking.py ...                                           [ 17%]
   tests/unit/test_models.py .....                                          [ 31%]
   tests/unit/test_services.py ....................                          [ 91%]
   tests/integration/test_books_api.py .......                              [ 100%]

   ========================= 34 passed in 0.52s ==============================

   ---------- coverage: platform linux, python 3.11.9 ----------
   Name                              Stmts   Miss  Cover   Missing
   ---------------------------------------------------------------
   src/bookshelf/__init__.py             0      0   100%
   src/bookshelf/database.py            14      0   100%
   src/bookshelf/isbn_service.py         6      0   100%
   src/bookshelf/main.py                10      0   100%
   src/bookshelf/models.py              23      0   100%
   src/bookshelf/routers/books.py       26      4    85%   32, 38-39, 52
   src/bookshelf/routers/reviews.py     14      2    86%   18, 25
   src/bookshelf/services.py            42      0   100%
   ---------------------------------------------------------------
   TOTAL                               135      6    96%

The output shows:

- **Stmts** — total executable statements in the file
- **Miss** — statements not executed by any test
- **Cover** — percentage covered
- **Missing** — line numbers not executed

Lines 32, 38-39, and 52 in ``routers/books.py`` were never executed. Open the file and
look at those lines — they reveal which cases your tests do not cover.

-----

Reading the HTML Report
------------------------

The ``term-missing`` output lists line numbers, but for larger files, the HTML report
is more useful:

.. code-block:: bash

   $ pytest --cov=bookshelf --cov-report=html tests/
   ...
   Coverage HTML written to dir htmlcov

Open ``htmlcov/index.html`` in a browser. Each file shows covered lines in green,
missed lines in red, and partially-covered branches in yellow.

Partially covered branches are especially useful: a line like ``return x if condition
else y`` may be executed (line covered) but only one branch actually runs. Branch
coverage reveals this:

.. code-block:: bash

   $ pytest --cov=bookshelf --cov-report=html --cov-branch tests/

The same view is available directly in GitHub. Once CI uploads coverage reports to
`Codecov <https://about.codecov.io/>`_, the
`Codecov browser extension <https://github.com/codecov/codecov-browser-extension>`_
(Chrome and Firefox) overlays covered and missed lines on files and pull requests —
useful during code review, when you want to see whether the changed lines are tested.

-----

What Coverage Does Not Tell You
---------------------------------

Coverage measures execution, not correctness.

**A covered line with a wrong assertion is still wrong:**

.. code-block:: python

   def test_average_rating_covered_but_wrong():
       result = services.calculate_average_rating([5, 3, 4])
       assert result is not None   # line is "covered" — result is 4.0, which is not None

The function is covered. The result is not verified. The assertion would pass even if
the function returned ``999.0``.

**A test that always passes is not a safety net:**

.. code-block:: python

   def test_create_book_covered():
       services.create_book(db_conn, sample_book)
       # No assertion — the call was covered, nothing was verified

**Coverage cannot detect missing tests:** if a feature was never implemented, there is no
code to cover — and coverage will not notice the gap.

.. admonition:: Observation:

   Coverage is best used to find what you have *not* tested, not to confirm what you have
   tested correctly. A gap in coverage is a signal to write a test. Full coverage is not
   a signal that tests are correct.

-----

Reasonable Coverage Targets
------------------------------

Different parts of a codebase warrant different targets:

- **Business logic and service functions:** aim for 90%+ line and branch coverage.
  Every validation rule, every conditional path, every error case should have a test.
  The BookShelf API's ``services.py`` should be close to 100%.

- **Route handlers:** 80-90% is reasonable. Error branches (missing database rows,
  duplicate ISBNs) should be covered by integration tests.

- **Infrastructure code** (``database.py``, ``main.py``): lower targets are acceptable.
  Connection management and lifespan hooks are hard to test in isolation and are
  exercised by the integration tests anyway.

- **Startup/configuration code:** often untestable in unit tests without significant
  mocking. Accept lower coverage here.

The industry standard for production services is 80% as a minimum gate. This is a
floor, not a target — the goal is covering critical paths, not chasing a percentage.

-----

Configuring Coverage in ``pyproject.toml``
--------------------------------------------

Hardcoding coverage flags on the command line is fragile — they get dropped. Configure
coverage in ``pyproject.toml``:

.. code-block:: toml

   [tool.coverage.run]
   source = ["bookshelf"]
   branch = true
   omit = [
       "*/tests/*",
       "*/__init__.py",
   ]

   [tool.coverage.report]
   fail_under = 80
   show_missing = true
   skip_covered = false

With this configuration, running ``pytest --cov`` (without extra flags) uses the
configured source and report settings. The ``fail_under = 80`` line causes pytest to
exit with a non-zero status code if coverage drops below 80% — essential for CI/CD.

The full command in the regression pipeline becomes:

.. code-block:: bash

   $ pytest --cov --cov-report=term-missing

If coverage falls below 80%:

.. code-block:: bash

   ---------- coverage: platform linux, python 3.11.9 ----------
   ...
   TOTAL                               135     27    80%

   FAIL Required test coverage of 80% not reached. Total coverage: 79.26%

The non-zero exit code causes the CI pipeline to fail.

-----

**Exercise**

#. Add the ``[tool.coverage.run]`` and ``[tool.coverage.report]`` sections to
   ``pyproject.toml`` as shown above, with ``fail_under = 80``.

#. Run coverage and identify the uncovered lines:

   .. code-block:: bash

      $ pytest --cov --cov-report=term-missing tests/

   Note every file with uncovered lines. Open each file and identify which code paths
   your tests do not exercise.

#. Write tests to cover the gaps. Common places to check:

   - The ``PUT /books/{id}`` and ``DELETE /books/{id}`` success paths
   - The ``GET /books/search`` endpoint
   - The ``POST /books/{id}/reviews`` for a non-existent book (404 path)

   Run coverage again. Verify the total is above 80%.

#. Generate the HTML report and open ``htmlcov/index.html`` in a browser. Identify any
   partially-covered branches (yellow lines). Write a test for at least one branch gap.
