.. _ch05_actions_basics:

GitHub Actions Fundamentals
============================

.. admonition:: Crash Course: YAML Syntax
   :class: dropdown

   Workflows are YAML files. YAML is a superset of JSON that uses **indentation** for
   structure. Three building blocks cover almost everything:

   .. code-block:: yaml

      # A mapping (dict): key, colon, space, value
      name: CI
      timeout-minutes: 10

      # Nesting is indentation (spaces only, never tabs; 2 spaces is the convention)
      on:
        push:
          branches: [main]        # flow-style sequence, like JSON
        pull_request:
          branches:               # block-style sequence: one "- " per item
            - main
            - release/*

      # A sequence of mappings: each "- " starts a new item
      steps:
        - uses: actions/checkout@v7
        - name: Run tests
          run: pytest -v

      # Multi-line strings: "|" keeps newlines (use it for shell scripts)
      run: |
        pip install -r requirements-dev.lock
        make lint

   **Strings usually need no quotes, which is exactly what bites you.** YAML guesses the
   type of every unquoted value. Here is what a YAML parser makes of a typical matrix:

   .. code-block:: bash

      $ python3 -c 'import yaml; print(yaml.safe_load(open("ci.yml")))'
      {True: {'push': {'branches': ['main']}}, 'jobs': {'test': {'strategy':
      {'matrix': {'python-version': [3.9, 3.1, 3.11, '3.12']}}, ...}}}

   Two surprises. ``3.10`` became the float ``3.1``, so ``setup-python`` would install
   Python 3.1. And the ``on:`` key became the boolean ``True``: PyYAML follows YAML 1.1,
   where ``on``/``off``/``yes``/``no`` are booleans. GitHub's parser treats ``on`` as a
   key, but your own scripts that read workflow files may not. Rule: **quote version
   numbers** (``"3.10"``) and anything that looks like a number, boolean or date.

   A colon followed by a space inside an unquoted value starts a new mapping:

   .. code-block:: yaml

      - run: echo "Thanks for the PR: ${{ github.event.pull_request.title }}"

   .. code-block:: text

      greet.yml:7:36: could not parse as YAML: mapping values are not allowed in this context

   Use a block scalar (``run: |``) for any shell command that contains ``:``, ``#`` or
   quotes.

   **Anchors and aliases** reuse a node: ``&name`` defines it, ``*name`` repeats it.
   GitHub Actions and GitLab CI both accept them. Use them sparingly, because a
   workflow full of aliases is hard to review:

   .. code-block:: yaml

      steps:
        - &checkout
          uses: actions/checkout@v7
      # later, in another job:
      steps:
        - *checkout

   For a deeper dive, see: `Learn YAML in Y minutes <https://learnxinyminutes.com/docs/yaml/>`_
   and the `YAML 1.2 specification <https://yaml.org/spec/1.2.2/>`_

-----

From Makefile to Machine
-------------------------

In :ref:`ch03_regression_pipeline` you wrote ``make all`` and promised yourself to run it
before every push. GitHub Actions removes the promise: a server runs the checks on every
push, for everyone, and posts the result on the commit and the pull request.

Workflows live in the repository, under ``.github/workflows/``. Every ``.yml`` file in
that directory is a separate workflow. GitHub picks them up automatically; there is
nothing to install or register.

-----

The Vocabulary
---------------

.. code-block:: text

   event (push to main)
     │
     ▼
   workflow  .github/workflows/ci.yml
     ├── job: lint      ──▶ runner VM #1 ── step: checkout ─▶ step: setup-python ─▶ step: make lint
     └── job: test      ──▶ runner VM #2 ── step: checkout ─▶ step: setup-python ─▶ step: pytest

**Event (trigger)**
   What starts a workflow: a push, a pull request, a schedule, a manual click.

**Workflow**
   One YAML file. Contains one or more jobs.

**Job**
   A set of steps that run **on the same machine**, in order. Jobs run **in parallel**
   by default, each on its **own fresh machine**. They share nothing (no files, no
   installed packages) unless you pass data explicitly.

**Step**
   One unit of work inside a job: either a shell command (``run:``) or a reusable
   **action** (``uses:``). Steps in a job share the filesystem and run sequentially; if
   one fails, the rest of the job is skipped.

**Runner**
   The machine that executes a job. GitHub-hosted runners are throwaway VMs, created
   for one job and destroyed after it.

**Action**
   A reusable, versioned step published in a Git repository, e.g.
   ``actions/checkout@v7``. Think of it as a library function for workflows.

-----

Your First Workflow
--------------------

Create ``.github/workflows/ci.yml`` in the BookShelf repository:

.. code-block:: yaml

   name: CI

   on:
     push:
       branches: [main]
     pull_request:
       branches: [main]

   jobs:
     test:
       runs-on: ubuntu-24.04
       steps:
         - uses: actions/checkout@v7
         - uses: actions/setup-python@v7
           with:
             python-version: "3.12"
         - run: pip install -e ".[dev]"
         - run: pytest -v

Line by line:

- ``name: CI`` is the workflow's display name in the Actions tab and in PR checks.
- ``on:`` runs on pushes to ``main`` and on pull requests that **target** ``main``.
  For a pull request, GitHub tests the **merge result** of the PR branch and ``main``,
  not just the branch, so you find out whether the code works after merging.
- ``runs-on: ubuntu-24.04`` is a fresh Ubuntu 24.04 VM. It comes with ``git``,
  ``make``, Docker, several Python versions and much more preinstalled.
- ``actions/checkout@v7``: the VM starts **empty**. This action clones your repository
  at the commit that triggered the run. Forgetting it is the most common first-workflow
  bug: every later step fails with "file not found".
- ``actions/setup-python@v7`` installs the requested Python and puts it on ``PATH``.
  The production image uses Python 3.12 (:ref:`ch04_multistage`), so CI does too. Test
  on the version you ship.
- ``run:`` executes a shell command (``bash`` on Linux runners, with ``-e``: the first
  failing command fails the step).

Commit and push it:

.. code-block:: bash

   $ mkdir -p .github/workflows
   $ $EDITOR .github/workflows/ci.yml
   $ git add .github/workflows/ci.yml
   $ git commit -m "ci: run tests on GitHub Actions"
   $ git push

-----

Watching It Run
----------------

Open the repository on GitHub and click the **Actions** tab. Within a few seconds a run
appears, named after your commit message:

.. code-block:: text

   ┌ Actions ───────────────────────────────────────────────────────────────────┐
   │ All workflows          │  ● ci: run tests on GitHub Actions                │
   │   CI                   │    CI #1: Commit 5d41a7e pushed by <you>   main   │
   │                        │    ⏱ In progress                                 │
   └────────────────────────────────────────────────────────────────────────────┘

Click the run, then the ``test`` job, to see the live log. Every step is a collapsible
section with its own timing:

.. code-block:: text

   test
   succeeded 41 seconds ago in 38s

   > ✓ Set up job                                      1s
   > ✓ Run actions/checkout@v7                         1s
   > ✓ Run actions/setup-python@v7                     2s
   > ✓ Run pip install -e ".[dev]"                    21s
   v ✓ Run pytest -v                                   9s
       1 ▶ Run pytest -v
       2 ============================= test session starts ==============================
       3 platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0 -- /opt/hostedtoolcache/Python/3.12.16/x64/bin/python
       ...
      84 tests/unit/test_validation.py::test_year_validation[3000-True] PASSED    [100%]
      85
      86 ======================== 80 passed, 1 warning in 2.71s =========================
   > ✓ Post Run actions/setup-python@v7                0s
   > ✓ Post Run actions/checkout@v7                    0s
   > ✓ Complete job                                    0s

The commit on the repository's main page now has a green check mark (✓) next to it.
Hover over it to see which checks ran. Note where the time went: 21 of 38 seconds were
``pip install``. You will cache that in :ref:`ch05_full_pipeline`.

.. admonition:: Observation:

   Each job starts on a brand-new VM, so nothing from your laptop leaks in: no
   ``.venv``, no stray ``bookshelf.db``, no environment variable you exported last
   week. Tests that pass locally but fail here usually depend on exactly that kind of
   hidden local state. CI is the first place your code runs on a machine that is not
   yours.

-----

Watching It Fail
-----------------

A pipeline is only useful if it goes red when it should. Break a test on purpose, for
example in ``tests/unit/test_services.py`` change the expected average in
``test_average_rating_multiple_reviews`` from ``4.0`` to ``3.0``, and push:

.. code-block:: text

   test
   failed 12 seconds ago in 36s

   v ✗ Run pytest -v                                    9s
      ...
      52 FAILED tests/unit/test_services.py::test_average_rating_multiple_reviews - assert 4.0 == 3.0
      53 =================== 1 failed, 79 passed, 1 warning in 2.84s ===================
      54 Error: Process completed with exit code 1.

The run, the commit, and (if there is one) the pull request get a red cross (✗). By
default GitHub also **emails** the person who pushed. The log line number is a link you
can paste into a chat or an issue.

The failure is reproducible locally with the same command, ``pytest -v``. Fix the test
and push again. A new run starts automatically and turns the commit green.

.. note::

   You can re-run a failed run from the UI (**Re-run jobs → Re-run failed jobs**)
   without pushing. That is the right tool for an infrastructure hiccup, such as a
   package index timeout. It is the *wrong* tool for a flaky test. If a test passes on
   the second try, it is telling you about a race condition or a hidden dependency
   (:ref:`ch03_test_isolation`), and re-running teaches the team to ignore red builds.

-----

Triggers
---------

The ``on:`` key accepts many events. Four cover most needs:

.. code-block:: yaml

   on:
     push:
       branches: [main]
       paths-ignore: ["**.md", "docs/**"]   # skip runs for doc-only changes
     pull_request:
       branches: [main]
     schedule:
       - cron: "17 3 * * *"                 # every day at 03:17 UTC
     workflow_dispatch:                     # a "Run workflow" button in the UI

``push`` / ``pull_request``
   The core CI triggers. Filter by ``branches``, ``tags`` and ``paths``.

``schedule``
   Cron syntax, **always UTC**, and only on the default branch. Useful for a nightly
   run that catches breakage from outside your repository: a new release of a
   dependency, an expired certificate, an upstream API change. Pick an odd minute: at
   ``0 0 * * *`` every repository on GitHub is queuing jobs, and scheduled runs may
   start late or be dropped under load. GitHub disables scheduled workflows in public
   repositories after 60 days without activity.

``workflow_dispatch``
   Adds a **Run workflow** button to the Actions tab. It can declare ``inputs:`` (for
   example, which environment to deploy to), which the UI renders as a form.

.. warning::

   There is also ``pull_request_target``. It looks like ``pull_request``, but it runs in
   the context of the **base** repository, with access to secrets and a write-capable
   token, even for pull requests from forks. Combined with checking out the PR's code,
   it lets any stranger run code with your secrets. Do not use it until you have read
   :ref:`ch05_secrets_environments`, and preferably not at all.

-----

Runners
--------

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * - Label
     - What you get
     - Use for
   * - ``ubuntu-24.04``
     - Linux VM, 4 vCPU, 16 GB RAM (public repos)
     - Almost everything. Same OS family as the container.
   * - ``ubuntu-latest``
     - Whatever Ubuntu GitHub currently calls "latest"
     - Convenience. It moves to a new release without warning.
   * - ``macos-latest``, ``windows-latest``
     - macOS / Windows VMs
     - Testing desktop tools and CLIs on those OSes. Billed at a higher rate.
   * - ``self-hosted``
     - A machine you register and operate
     - Special hardware (GPUs), private network access, cost control at scale

``ubuntu-latest`` is to runners what ``python:3.12-slim`` is to base images (see
:ref:`ch04_multistage`): a moving tag. When GitHub moves it to a newer Ubuntu, preinstalled
tool versions change under you. The BookShelf workflows pin ``ubuntu-24.04`` and upgrade
deliberately.

.. warning::

   **Never attach self-hosted runners to a public repository.** Anyone can open a pull
   request, and a workflow triggered by that PR runs the PR's code on *your* machine.
   Unlike GitHub-hosted VMs, a self-hosted runner is not wiped between jobs: whatever
   the first job leaves behind (a backdoor, a modified ``~/.bashrc``), the next job,
   possibly a deployment with production secrets, inherits.

-----

Actions: Reusable Steps
------------------------

``uses: owner/repo@ref`` runs the action defined in that repository at that Git ref. The
official ones live under ``actions/`` (maintained by GitHub) and ``docker/`` (maintained
by Docker). Thousands more are on the `GitHub Marketplace <https://github.com/marketplace?type=actions>`_.

.. code-block:: yaml

   - uses: actions/checkout@v7          # major version tag: gets fixes, no breaking changes
   - uses: actions/checkout@v7.0.1      # exact release tag
   - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1   # v7.0.1, immutable

Inputs are passed with ``with:``. Each action documents its inputs in the ``action.yml``
file at the root of its repository. That file is the authoritative reference, more
reliable than blog posts written for an older major version.

.. admonition:: Observation:

   An action is code you run inside your pipeline, with your token and, in deployment
   jobs, your secrets. A **tag** like ``@v7`` is a pointer the action's owner can move
   at any time. :ref:`ch05_secrets_environments` shows what happens when an attacker
   moves it, and how to pin by commit SHA instead.

-----

Status Badges
--------------

Each workflow publishes a badge image. Add it to the top of ``README.md``:

.. code-block:: text

   [![CI](https://github.com/<you>/bookshelf/actions/workflows/ci.yml/badge.svg)](https://github.com/<you>/bookshelf/actions/workflows/ci.yml)

It shows the status of the latest run on the default branch. A badge is a small social
contract: a red badge on a project's front page gets noticed.

-----

Catching Workflow Mistakes Before Pushing
------------------------------------------

The feedback loop "edit YAML → commit → push → wait → read error" is slow. `actionlint
<https://github.com/rhysd/actionlint>`_ is a static checker for workflow files. It knows
the workflow schema, checks expressions and references between jobs, and runs
``shellcheck`` on every ``run:`` script. The Docker image needs no installation:

.. code-block:: bash

   $ docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.12 -no-color
   .github/workflows/ci.yml:11:3: job "test" needs job "lnit" which does not exist in this workflow [job-needs]
      |
   11 |   test:
      |   ^~~~~

A typo like this passes YAML parsing. Without actionlint you would only find it after
pushing. No output means no problems found.

You can add actionlint as a pre-commit hook (:ref:`ch01_precommit`) with the hook from
the actionlint repository, so workflow mistakes are caught before they are even committed.

-----

**Exercises**

#. Create ``.github/workflows/ci.yml`` with the minimal workflow above, commit and push
   it. Open the Actions tab and watch the run. Then answer, from the log:

   - Which Python patch version did ``setup-python`` install?
   - How long did ``pip install`` take compared to ``pytest``?
   - How many tests ran?

#. Break a test intentionally (change an expected value in
   ``tests/unit/test_services.py``). Push and observe:

   - the red ✗ on the commit in the repository's commit list
   - the exact log line where pytest reports the failure
   - the notification email (check your inbox)

   Reproduce the failure locally with the same command, fix the test, push, and confirm
   the run turns green.

#. Run ``actionlint`` on your repository with the Docker command above. Then introduce
   two mistakes, ``needs: lnit`` and an unquoted ``run: echo "Note: done"``, run it
   again, and read both errors. Fix them before you commit.

#. Add ``workflow_dispatch:`` to the triggers, push, and start a run manually from the
   Actions tab with **Run workflow**.

#. Add the status badge to ``README.md`` (create the file if needed) and verify that it
   renders on the repository's front page.

#. **(Optional)** Add a ``schedule`` trigger that runs the workflow every night at an
   odd minute past 03:00 UTC. Why does a nightly run of *unchanged* code make sense for a
   project whose dependency versions are not fully pinned?
