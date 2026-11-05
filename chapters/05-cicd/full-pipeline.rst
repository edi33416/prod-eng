.. _ch05_full_pipeline:

Building the Full Pipeline
===========================

Automating What We Did Manually
--------------------------------

The workflow from :ref:`ch05_actions_basics` runs the tests and nothing else. The
regression pipeline you built in :ref:`ch03_regression_pipeline` and extended in
Chapter 4 does more. This page turns every one of those manual checks into a CI job:

.. list-table::
   :header-rows: 1
   :widths: 32 30 38

   * - You ran this by hand…
     - …CI runs it in job
     - Notes
   * - ``make lint``
     - ``lint``
     - ``ruff check`` + ``ruff format --check``
   * - ``make typecheck``
     - ``lint``
     - ``pyright src/``
   * - ``make test`` + ``make integration``
     - (covered by ``test``)
     - Subsets of ``make coverage``; keep them for fast local runs
   * - ``make coverage``
     - ``test``
     - All 80 tests, fails below 80 % coverage, writes ``coverage.xml``
   * - ``make test-pg``
     - ``test-pg``
     - GitHub provides the PostgreSQL container
   * - ``docker build``
     - ``build``
     - The multi-stage image from :ref:`ch04_multistage`

The rule from :ref:`ch05_cicd_concepts` applies throughout: **CI calls the same Make
targets you call**. If CI is red, the same ``make`` command reproduces it on your
machine.

-----

Step 1: Add the Lint Job and Watch It Fail
-------------------------------------------

Add a ``lint`` job next to ``test`` in ``.github/workflows/ci.yml``:

.. code-block:: yaml

   jobs:
     lint:
       name: lint
       runs-on: ubuntu-24.04
       steps:
         - uses: actions/checkout@v7
         - uses: actions/setup-python@v7
           with:
             python-version: "3.12"
         - run: pip install -e ".[dev]"
         - run: make lint
         - run: make typecheck

     test:
       # ... unchanged ...

Push it. The ``test`` job is green, as before. The ``lint`` job is **red**:

.. code-block:: text

   v ✗ Run make lint
       1 ▶ Run make lint
       2 ruff check .
       3 E501 Line too long (94 > 88)
       4   --> src/bookshelf/routers/books.py:32:89
       5    |
       6 30 | @router.get("/top", response_model=list[BookResponse])
       7 31 | def top_books_endpoint(
       8 32 |     n: int = Query(default=5, ge=1, le=50, description="Number of top-rated books to return"),
       9    |                                                                                         ^^^^^^
      10 33 | ) -> list[BookResponse]:
         ...
     187 Found 19 errors.
     188 make: *** [Makefile:4: lint] Error 1
     189 Error: Process completed with exit code 2.

Nineteen lines too long, in code that has passed every test for four chapters. Run
``ruff format --check .`` locally and it gets worse:

.. code-block:: bash

   $ ruff format --check .
   ...
   9 files would be reformatted, 13 files already formatted

How did this happen, when ``make lint`` has existed since Chapter 3 and pre-commit
hooks since Chapter 1? Because both were **voluntary**:

- pre-commit hooks only run in a clone where someone ran ``pre-commit install``. A new
  team member, a fresh clone, or a ``git commit --no-verify`` skips them silently.
- ``make all`` runs when a developer remembers to run it. Under deadline pressure, people
  run the tests they think are relevant, and nobody runs the linter.
- No single change was the problem. Each one added a long line or two, and the debt grew
  one commit at a time.

This is the most common outcome of adding CI to an existing project, and the main
argument for adding it on day one. A check that nobody is forced to pass is not a check.

.. admonition:: Observation:

   The ``test`` job passed and the ``lint`` job failed **independently**: jobs without
   ``needs:`` run in parallel and do not affect each other. You see every problem in a
   single run, not one at a time.

-----

Step 2: Pay Down the Debt
--------------------------

Add a ``format`` target to the ``Makefile`` (next to ``lint``) so that the fix is as easy
to run as the check:

.. code-block:: makefile

   format:
   	ruff format .
   	ruff check --fix .

.. code-block:: bash

   $ make format
   ruff format .
   9 files reformatted, 13 files left unchanged
   ruff check --fix .
   All checks passed!

   $ git diff --stat
    src/bookshelf/routers/books.py        |   4 +-
    src/bookshelf/services.py             | 112 ++++++++++++++---------
    tests/conftest.py                     |  38 ++++++--
    tests/integration/test_books_api.py   | 168 +++++++++++++++++++++-------------
    tests/integration/test_reviews_api.py |  94 ++++++++++++-------
    tests/unit/test_isbn_service.py       |   4 +-
    tests/unit/test_mocking.py            |  12 ++-
    tests/unit/test_services.py           |  12 ++-
    tests/unit/test_validation.py         |  16 ++--
    9 files changed, 296 insertions(+), 164 deletions(-)

The formatter fixed all 19 ``E501`` errors on its own: every overlong line was code that
could be wrapped. Run the tests to confirm that formatting changed only layout, then
commit the result **on its own**:

.. code-block:: bash

   $ make coverage
   ...
   ======================== 80 passed, 1 warning in 2.58s =========================
   $ git commit -am "style: apply ruff format to the whole codebase"

.. note::

   Keep mass reformatting in a commit with no other changes. Reviewers can skip it, and
   you can list its hash in a ``.git-blame-ignore-revs`` file so that ``git blame`` (and
   GitHub's blame view) looks past it to the commit that actually wrote each line.

-----

Step 3: Pin the Tools
----------------------

``pip install -e ".[dev]"`` installs whatever versions satisfy ``ruff>=0.5`` and
``pyright>=1.1`` **today**. Ruff ships new releases frequently, and new releases
sometimes change formatting or add lint rules. With unpinned tools, a release on a
Tuesday night can turn every open pull request red on Wednesday morning, even though
nobody changed any code. Worse, your laptop and CI disagree, and "it passes locally"
stops meaning anything.

The runtime dependencies are already pinned in ``requirements.lock``
(:ref:`ch04_dockerfile`). Do the same for the development tools: compile the ``dev``
extra into a second lockfile.

.. code-block:: bash

   $ pip install pip-tools
   $ pip-compile --extra dev --strip-extras --constraint requirements.lock \
       --output-file=requirements-dev.lock pyproject.toml
   $ grep -E '^(ruff|pyright|pytest|pytest-cov|psycopg-binary)==' requirements-dev.lock
   psycopg-binary==3.3.6
   pyright==1.1.414
   pytest==9.2.0
   pytest-cov==7.1.0
   ruff==0.17.3

``requirements-dev.lock`` contains the runtime dependencies **and** the dev tools, all
pinned. ``--constraint requirements.lock`` is essential. Without it, ``pip-compile``
resolves the runtime dependencies again, picks whatever is newest **today**, and CI
ends up testing different library versions from the ones the Docker image ships. When
this chapter was written, that happened to nine packages, among them ``psycopg-binary``
(3.3.8 in the dev lock, 3.3.6 in the image) and ``sqlalchemy``. With the constraint,
every package that both files contain has the same version in each:

.. code-block:: bash

   $ grep -A2 '^psycopg-binary==' requirements-dev.lock
   psycopg-binary==3.3.6
       # via
       #   -c requirements.lock

Developers and CI install from it:

.. code-block:: bash

   $ pip install -r requirements-dev.lock   # every dependency, pinned
   $ pip install --no-deps -e .             # the bookshelf package itself, nothing else

Upgrading a tool is now a deliberate change: re-run ``pip-compile`` with
``--upgrade-package ruff``, run ``make lint``, fix whatever the new version complains
about, and commit both together. The upgrade arrives as a reviewed PR, not as a surprise.

Add ``requirements-dev.lock`` and ``.github/`` to ``.dockerignore``. Neither belongs in
the production image, and changing them should not invalidate the image's build cache.

-----

Step 4: The Test Jobs
----------------------

``test`` runs the whole suite once, with coverage:

.. code-block:: yaml

   test:
     name: test
     runs-on: ubuntu-24.04
     timeout-minutes: 10
     steps:
       - uses: actions/checkout@v7
       - uses: actions/setup-python@v7
         with:
           python-version: "3.12"
           cache: pip
           cache-dependency-path: requirements-dev.lock
       - name: Install dependencies
         run: |
           pip install -r requirements-dev.lock
           pip install --no-deps -e .
       - name: make coverage
         run: make coverage
       - name: Upload coverage report
         if: ${{ !cancelled() }}
         uses: actions/upload-artifact@v7
         with:
           name: coverage-report
           path: coverage.xml
           retention-days: 14

Two details:

- ``make coverage`` now also writes ``coverage.xml``. Extend the target in the
  ``Makefile`` with ``--cov-report=xml``, and add ``coverage.xml`` to ``.gitignore`` and
  ``.dockerignore``. The XML format is what coverage services and PR comment bots
  consume.
- ``if: ${{ !cancelled() }}`` uploads the report **even when tests fail**. By default a
  step runs only if all previous steps succeeded. A coverage report from a failing run is
  exactly the one you want to look at.

``test-pg`` is the CI version of ``make test-pg``. In Chapter 4 you started PostgreSQL
with ``docker-compose.test.yml``. In GitHub Actions, a job can declare **service
containers**: GitHub starts them before the first step, waits for their health check,
and removes them when the job ends.

.. code-block:: yaml

   test-pg:
     name: test-pg
     runs-on: ubuntu-24.04
     timeout-minutes: 10
     # Same role as docker-compose.test.yml: a throwaway PostgreSQL for the suite.
     services:
       postgres:
         image: postgres:16-alpine
         env:
           POSTGRES_USER: test
           POSTGRES_PASSWORD: test
           POSTGRES_DB: bookshelf_test
         ports:
           - 5432:5432
         options: >-
           --health-cmd "pg_isready -U test -d bookshelf_test"
           --health-interval 2s
           --health-timeout 3s
           --health-retries 10
     env:
       TEST_DATABASE_URL: postgresql://test:test@localhost:5432/bookshelf_test
     steps:
       # checkout, setup-python, install, exactly as in "test"
       - name: pytest against PostgreSQL
         run: pytest tests/

Compare it with ``docker-compose.test.yml``: same image, same credentials, same
``pg_isready`` health check. ``options:`` passes extra flags to ``docker run``. The job's
steps run directly on the runner VM, not in a container, so they reach PostgreSQL through
the published port on ``localhost``. The ``db_engine`` fixture from Chapter 4 reads
``TEST_DATABASE_URL`` and runs all 80 tests against PostgreSQL instead of SQLite.

.. admonition:: Observation:

   The test password ``test`` is in plain text in the workflow file, and that is fine.
   It protects a database that exists for two minutes, holds only test data, and is
   reachable only from inside the runner VM. Secrets are for credentials that grant
   access to something real (:ref:`ch05_secrets_environments`).

The case-insensitive search regression from :ref:`ch04_migrate_postgres` passed on
SQLite and failed only on PostgreSQL. With ``test-pg`` in CI, a bug like that can no
longer reach ``main`` because someone skipped ``make test-pg``.

-----

Step 5: Job Dependencies
-------------------------

By default, jobs start in parallel. ``needs:`` makes one job wait for others and run
**only if they all succeeded**:

.. code-block:: yaml

   build:
     name: build
     needs: [lint, test, test-pg]
     runs-on: ubuntu-24.04

GitHub draws the resulting graph on the run's summary page:

.. code-block:: text

   ┌──────────────┐
   │ ✓ lint   22s │──┐
   └──────────────┘  │
   ┌──────────────┐  │    ┌───────────────┐
   │ ✓ test   31s │──┼───▶│ ✓ build   48s │
   └──────────────┘  │    └───────────────┘
   ┌──────────────┐  │
   │ ✓ test-pg 34s│──┘
   └──────────────┘

There are two ways to shape this graph, and they trade time against compute:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * -
     - ``lint`` → ``test`` → ``build`` (sequential)
     - ``lint`` ∥ ``test`` ∥ ``test-pg`` → ``build``
   * - Wall-clock time
     - Sum of all jobs
     - Slowest check + build
   * - Runner minutes spent on a lint failure
     - Lint only. Tests never start.
     - All three checks run anyway
   * - Feedback on a PR with several problems
     - One problem per push
     - Every problem in one run

Many pipelines chain ``test`` after ``lint`` (``needs: lint``) to avoid running tests on
code that does not even pass the linter. BookShelf runs the checks in parallel instead,
because waiting is more expensive than runner minutes, and public repositories get those
minutes free. A team with an hour-long test suite on paid runners
might choose the opposite. Either way, ``build`` comes last: there is no point building
an image from code that fails its checks.

-----

Step 6: Build the Image
------------------------

.. code-block:: yaml

   build:
     name: build
     needs: [lint, test, test-pg]
     runs-on: ubuntu-24.04
     timeout-minutes: 15
     steps:
       - uses: actions/checkout@v7
       - uses: docker/setup-buildx-action@v4
       - name: Build image (not pushed)
         uses: docker/build-push-action@v7
         with:
           context: .
           push: false
           tags: bookshelf:${{ github.sha }}
           cache-from: type=gha
           cache-to: type=gha,mode=max

``docker/setup-buildx-action`` configures BuildKit, the builder you used in Chapter 4.
``docker/build-push-action`` runs the equivalent of ``docker build``. With
``push: false`` the image is built and then discarded. The job answers one question:
*does the Dockerfile still build from this commit?* A dependency that no longer installs
on the slim base image, or a ``COPY`` of a file that was renamed, fails here, on the
pull request, not at release time. :ref:`ch05_docker_in_ci` pushes the image.

``${{ github.sha }}`` is an **expression**. GitHub substitutes the full 40-character
commit SHA before the step runs. Expressions can read **contexts**: ``github`` (event,
repository, ref, SHA, actor), ``env``, ``secrets``, ``needs`` (outputs of upstream
jobs), ``runner``, and others.

-----

Step 7: Caching
----------------

Every job starts on an empty VM, so every job downloads every package again. Caching
saves files from one run and restores them in a later run when a **key** matches.

``setup-python`` has caching built in:

.. code-block:: yaml

   - uses: actions/setup-python@v7
     with:
       python-version: "3.12"
       cache: pip
       cache-dependency-path: requirements-dev.lock

The cache key includes a hash of ``requirements-dev.lock``. As long as the lockfile does
not change, pip's download cache is restored and ``pip install`` reads wheels from disk:

.. code-block:: text

   Run actions/setup-python@v7
     ...
     pip cache is not found                           ← first run: cache miss
   ...
   Post job cleanup.
     Cache saved with key: setup-python-Linux-x64-24.04-Ubuntu-python-3.12.16-pip-6b1f…

   # next run, same lockfile:
     Cache restored from key: setup-python-Linux-x64-24.04-Ubuntu-python-3.12.16-pip-6b1f…

Under the hood this is the general-purpose ``actions/cache`` action. Written out by hand,
it is the same mechanism, and you will need this form for anything ``setup-python``
does not know about:

.. code-block:: yaml

   - uses: actions/cache@v6
     with:
       path: ~/.cache/pip
       key: pip-${{ runner.os }}-py3.12-${{ hashFiles('requirements-dev.lock') }}
       restore-keys: |
         pip-${{ runner.os }}-py3.12-

``key`` must match exactly for a cache hit. ``restore-keys`` are prefixes to fall back
on: after a lockfile change, the newest cache from an older lockfile is restored, and
pip only downloads what changed.

For the Docker build, ``cache-from: type=gha`` / ``cache-to: type=gha,mode=max`` store
BuildKit's layer cache in the same GitHub cache service. ``mode=max`` also caches the
layers of the **builder** stage, which ``mode=min`` would skip. That stage holds
``pip install -r requirements.lock``, the slowest step. If only ``src/`` changed, the
dependency layers are reused, exactly as with local layer caching
(:ref:`ch04_layer_caching`).

.. list-table:: Cache vs artifact
   :header-rows: 1
   :widths: 20 40 40

   * -
     - Cache (``actions/cache``)
     - Artifact (``actions/upload-artifact``)
   * - Purpose
     - Speed up later runs
     - Keep an output of this run
   * - Contents
     - Reproducible inputs (packages, layers)
     - Results (reports, binaries, logs)
   * - If it is missing
     - Slower run, same result
     - Information is lost
   * - Visible in UI
     - Actions → Caches
     - The run's summary page, downloadable

.. warning::

   Never cache anything a run **produces as a result**, and never depend on a cache
   being present. GitHub evicts caches that have not been used for a week, and evicts
   the oldest ones when a repository exceeds its cache quota. A pipeline must give the
   same result, only slower, with an empty cache.

-----

Step 8: Guard Rails
--------------------

Three more top-level settings make the workflow safer and cheaper:

.. code-block:: yaml

   # A newer push to the same branch or PR cancels the run it supersedes.
   concurrency:
     group: ci-${{ github.ref }}
     cancel-in-progress: true

   # Least privilege: CI only needs to read the code.
   permissions:
     contents: read

``concurrency``
   Push three fixups in a minute and three full runs queue up. Only the last one
   matters. Runs in the same ``group`` cancel their predecessor.

``permissions``
   Every job receives an automatic ``GITHUB_TOKEN``. Here it is limited to reading the
   repository. :ref:`ch05_secrets_environments` explains why that matters.

``timeout-minutes`` (per job)
   The default is **360 minutes**. A test that deadlocks waiting for a database would
   burn six hours of runner time before GitHub kills it. Set a timeout a few times
   longer than the job's normal duration.

-----

The Complete CI Workflow
-------------------------

This is ``.github/workflows/ci.yml`` at this point in the chapter. The file in
``support/bookshelf-ch5-solution/`` has two more lines, the package index setting added in
:ref:`ch05_internal_package_index`:

.. code-block:: yaml

   # Continuous integration: the Chapter 3 regression pipeline, run by GitHub
   # on every push to main and every pull request targeting main.
   name: CI

   on:
     push:
       branches: [main]
     pull_request:
       branches: [main]
     workflow_dispatch:

   # A newer push to the same branch or PR cancels the run it supersedes.
   concurrency:
     group: ci-${{ github.ref }}
     cancel-in-progress: true

   # Least privilege: CI only needs to read the code.
   permissions:
     contents: read

   jobs:
     lint:
       name: lint
       runs-on: ubuntu-24.04
       timeout-minutes: 10
       steps:
         - uses: actions/checkout@v7
         - uses: actions/setup-python@v7
           with:
             python-version: "3.12"
             cache: pip
             cache-dependency-path: requirements-dev.lock
         - name: Install pinned dev tools
           run: pip install -r requirements-dev.lock
         - name: make lint
           run: make lint
         - name: make typecheck
           run: make typecheck

     test:
       name: test
       runs-on: ubuntu-24.04
       timeout-minutes: 10
       steps:
         - uses: actions/checkout@v7
         - uses: actions/setup-python@v7
           with:
             python-version: "3.12"
             cache: pip
             cache-dependency-path: requirements-dev.lock
         - name: Install dependencies
           run: |
             pip install -r requirements-dev.lock
             pip install --no-deps -e .
         - name: make coverage
           run: make coverage
         - name: Upload coverage report
           if: ${{ !cancelled() }}
           uses: actions/upload-artifact@v7
           with:
             name: coverage-report
             path: coverage.xml
             retention-days: 14

     test-pg:
       name: test-pg
       runs-on: ubuntu-24.04
       timeout-minutes: 10
       # Same role as docker-compose.test.yml: a throwaway PostgreSQL for the suite.
       services:
         postgres:
           image: postgres:16-alpine
           env:
             POSTGRES_USER: test
             POSTGRES_PASSWORD: test
             POSTGRES_DB: bookshelf_test
           ports:
             - 5432:5432
           options: >-
             --health-cmd "pg_isready -U test -d bookshelf_test"
             --health-interval 2s
             --health-timeout 3s
             --health-retries 10
       env:
         TEST_DATABASE_URL: postgresql://test:test@localhost:5432/bookshelf_test
       steps:
         - uses: actions/checkout@v7
         - uses: actions/setup-python@v7
           with:
             python-version: "3.12"
             cache: pip
             cache-dependency-path: requirements-dev.lock
         - name: Install dependencies
           run: |
             pip install -r requirements-dev.lock
             pip install --no-deps -e .
         - name: pytest against PostgreSQL
           run: pytest tests/

     build:
       name: build
       needs: [lint, test, test-pg]
       runs-on: ubuntu-24.04
       timeout-minutes: 15
       steps:
         - uses: actions/checkout@v7
         - uses: docker/setup-buildx-action@v4
         - name: Build image (not pushed)
           uses: docker/build-push-action@v7
           with:
             context: .
             push: false
             tags: bookshelf:${{ github.sha }}
             cache-from: type=gha
             cache-to: type=gha,mode=max

.. admonition:: Observation:

   The ``lint`` job does not run ``pip install -e .``, yet ``pyright src/`` still resolves
   ``from bookshelf import ...``: pyright adds ``src/`` to its import search path on its
   own. The ``lint`` job also never imports the code, so it does not need the package
   installed. The two test jobs do, because pytest imports ``bookshelf``.

-----

**Exercises**

#. Add the ``lint`` job to your workflow, using ``pip install -e ".[dev]"`` as in Step
   1. Push it and confirm it fails. Count the errors in the log and compare them with
   ``make lint`` on your machine.

#. Add the ``format`` target to the ``Makefile``, run ``make format``, run the tests,
   and commit the reformatting as a separate ``style:`` commit. Push and confirm the
   ``lint`` job turns green. Add the commit hash to a new ``.git-blame-ignore-revs``
   file.

#. Generate ``requirements-dev.lock`` with ``pip-compile`` as in Step 3 and switch all
   jobs to ``pip install -r requirements-dev.lock``. Which ruff version did you pin?
   Is it the same one you have installed locally (``ruff --version``)?

#. Implement the full pipeline: ``lint``, ``test``, ``test-pg`` and ``build``, with
   caching, ``concurrency``, ``permissions`` and timeouts. Push and verify on the run's
   summary page that:

   - the three check jobs start at the same time
   - ``build`` starts only after all three succeed
   - a ``coverage-report`` artifact is attached to the run; download it and open
     ``coverage.xml``

#. Push an empty commit (``git commit --allow-empty -m "ci: re-run"``) and compare the
   duration of the ``Install dependencies`` step with the previous run. Find the
   ``Cache restored from key`` line in the ``setup-python`` step.

#. Prove that ``needs`` gates the build. Add a deliberately failing assertion to an
   integration test and push. Which jobs ran, which failed, and what does the graph show
   for ``build``? Revert the change.

#. Prove that ``test-pg`` earns its place. Temporarily remove the ``LOWER()`` calls from
   ``search_books`` in ``services.py`` (the fix from :ref:`ch04_migrate_postgres`) and
   push. Which job fails and which passes? Revert.

#. **(Optional)** ``pyproject.toml`` declares ``requires-python = ">=3.11"``, but CI tests
   only 3.12. Turn the ``test`` job into a matrix:

   .. code-block:: yaml

      strategy:
        fail-fast: false
        matrix:
          python-version: ["3.11", "3.12", "3.13"]

   and use ``${{ matrix.python-version }}`` in ``setup-python``. What are the job names
   now? (Note them. They matter in :ref:`ch05_branch_protection`.) Does every version
   pass with the pinned lockfile? If not, what does that tell you about locking for
   multiple Python versions?
