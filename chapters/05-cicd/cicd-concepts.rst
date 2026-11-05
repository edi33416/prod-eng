.. _ch05_cicd_concepts:

CI/CD Concepts
===============

.. note::

   This chapter starts from the BookShelf API at the end of Chapter 4. A clean copy is
   provided in ``support/bookshelf-ch5/``. The finished state of the chapter, with
   workflows, a pinned dev-tool lockfile and a branch protection guide, is in
   ``support/bookshelf-ch5-solution/``. The two reference workflows are also in
   ``support/.github/workflows/``.

   You need a **GitHub account**, ``git``, and Docker (from Chapter 4). Use a **public**
   repository for the labs: GitHub Actions minutes and GitHub Container Registry storage
   are free for public repositories, while private repositories draw from a monthly
   quota. Nothing in this chapter deploys to a real server or cloud account.

-----

45 Minutes, 440 Million Dollars
--------------------------------

On 1 August 2012, Knight Capital, then one of the largest equity traders in the US,
rolled out new trading software to its eight production servers. The deployment was
manual. A technician copied the new code to seven of the servers. The eighth kept the
old binary.

The new release reused a configuration flag that, years earlier, had switched on a
retired feature called *Power Peg*. On seven servers the flag now enabled the new code.
On the eighth it woke up the dead code, which started buying high and selling low as fast
as it could. Nobody had a quick way to tell which version each server was running, or to
roll back reliably. By the time the eighth server was stopped, 45 minutes later, Knight
had lost about **$440 million**. The company was sold within months.

None of the individual mistakes was exotic. Each one is what happens when the path to
production depends on a person following a checklist:

- the deployment was not identical on every target
- nothing verified *what* was running after the deploy
- dead code was still in the build, reachable by configuration
- there was no rehearsed, automated rollback

CI/CD is the engineering answer: make the path from a commit to production **automated,
identical every time, and observable**, so that "did we deploy the same thing
everywhere?" has a recorded answer.

-----

Three Terms, Often Confused
----------------------------

**Continuous Integration (CI)**
   Every push is automatically built and tested against the shared main branch. A broken
   change is detected in minutes, by a machine, while its author still remembers what
   they changed, instead of days later by a colleague whose branch no longer merges.

**Continuous Delivery (CD)**
   Every change that passes CI produces a **release candidate**: a built, versioned
   artifact (for us, a container image) that *could* go to production right now.
   Actually deploying it to production is a **human decision**, often one button.

**Continuous Deployment**
   Every change that passes the pipeline goes to production **automatically**. No human
   approval step. This requires very high confidence in the test suite and in
   monitoring and rollback (Chapters 8–9).

.. code-block:: text

                    ┌─────────── Continuous Integration ───────────┐
   commit ──▶ push ──▶ lint ──▶ test ──▶ build image ──▶ push image ──▶ staging ──▶ production
                    └──────────────────── Continuous Delivery ───────────────────┘   ▲
                                                                                    │
                                                    Continuous Delivery:   a human approves
                                                    Continuous Deployment: automatic

The difference between the last two is a single gate. This chapter builds **continuous
delivery**: everything is automatic up to staging, and production waits for an
approval.

.. admonition:: Observation:

   "CD" is ambiguous in conversation. When someone says "we do CD", ask whether a human
   approves production deploys. The answer tells you a lot about their test coverage,
   their monitoring, and how much they trust both.

-----

The Pipeline
-------------

You have already built every stage of the pipeline by hand. This chapter makes GitHub
run them for you on every push.

.. list-table::
   :header-rows: 1
   :widths: 14 40 46

   * - Stage
     - What it does
     - Where you built it
   * - **lint**
     - ``ruff check``, ``ruff format --check``, ``pyright``
     - ``make lint`` / ``make typecheck``, :ref:`ch01_code_quality`, :ref:`ch03_regression_pipeline`
   * - **test**
     - unit + integration tests, coverage ≥ 80 %
     - ``make coverage``, :ref:`ch03_coverage`
   * - **test (PostgreSQL)**
     - the same suite against a real PostgreSQL
     - ``make test-pg``, :ref:`ch04_migrate_postgres`
   * - **build**
     - build the multi-stage image
     - ``docker build``, :ref:`ch04_multistage`
   * - **push**
     - publish the image to a registry, tagged with the commit SHA
     - new in this chapter
   * - **deploy**
     - roll the image out to staging, then production
     - new in this chapter (placeholder)

The order matters. Cheap, fast checks run first, so a missing import fails in 20 seconds
instead of after a three-minute image build. Each stage is a **quality gate**: if it
fails, nothing after it runs.

-----

Principles That Make a Pipeline Trustworthy
--------------------------------------------

A pipeline that is red half the time for no reason, or green when the code is broken, is
worse than none: people learn to ignore it. Five principles keep it honest.

**Same commands locally and in CI.**
   CI runs ``make lint`` and ``make coverage``, the same targets you run before pushing.
   When CI fails you can reproduce the failure with one command. The Makefile is the
   contract between developer and pipeline.

**Pin everything that can change.**
   Python version, tool versions, base images, runner OS, third-party actions. An
   unpinned linter that ships a new rule overnight turns every open PR red even though
   nobody touched the code.

**Build once, deploy many.**
   The image is built **once**, from a commit that passed CI, and the *same image* (same
   digest) is promoted to staging and then production. Rebuilding for each environment
   means production runs bytes that were never tested in staging.

**The pipeline is the only path to production.**
   If people can push images from laptops or ``ssh`` into servers to hot-fix them, the
   pipeline's guarantees are suggestions. Branch protection (end of this chapter) and
   registry permissions (Chapter 10) close the side doors.

**The pipeline is code.**
   Workflows live in ``.github/workflows/`` in the same repository, are reviewed in PRs,
   and have history. A change to the release process gets the same scrutiny as a change
   to the application.

-----

What This Chapter Builds
-------------------------

By the end of the chapter, BookShelf has two workflows and a protected ``main`` branch:

.. code-block:: text

   Pull request ─▶ CI:  ┌ lint ──────┐
                        ├ test ──────┼──▶ build (image, not pushed)
                        └ test-pg ───┘
                             │ all green + 1 approval
                             ▼
                        merge to main
                             │
   Push to main ─▶ CI (same jobs) ──success──▶ CD: build-and-push ──▶ deploy-staging ──▶ ⏸ approval ──▶ deploy-production
                                                   ghcr.io/<you>/bookshelf:<sha>

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Page
     - Adds
   * - :ref:`ch05_actions_basics`
     - A first workflow that runs the tests on GitHub
   * - :ref:`ch05_full_pipeline`
     - The full lint → test → build pipeline, pinned tools, caching
   * - :ref:`ch05_secrets_environments`
     - Secrets, ``staging`` / ``production`` environments, approval gates
   * - :ref:`ch05_docker_in_ci`
     - Building and pushing images to ``ghcr.io``
   * - :ref:`ch05_internal_package_index`
     - Installing dependencies from a curated internal package index
   * - :ref:`ch05_branch_protection`
     - Making CI a required gate for merging to ``main``
   * - :ref:`ch05_gitlab_ci`
     - The same pipeline in GitLab CI, for comparison

-----

Lab Setup: Put BookShelf on GitHub
------------------------------------

Every exercise in this chapter runs on GitHub, so the project needs a repository there.

1. On GitHub, create a new **public** repository named ``bookshelf``. Do **not**
   initialise it with a README, ``.gitignore`` or licence; you will push existing code.

2. Copy the starter and push it:

   .. code-block:: bash

      $ cp -r support/bookshelf-ch5 ~/bookshelf && cd ~/bookshelf
      $ git init -b main
      Initialized empty Git repository in /home/student/bookshelf/.git/
      $ git add .
      $ git commit -m "chore: import BookShelf API from chapter 4"
      [main (root-commit) 2b7e0c1] chore: import BookShelf API from chapter 4
       32 files changed, 1664 insertions(+)
       ...
      $ git remote add origin git@github.com:<you>/bookshelf.git
      $ git push -u origin main
      ...
      To github.com:<you>/bookshelf.git
       * [new branch]      main -> main
      branch 'main' set up to track 'origin/main'.

   If you already have your own BookShelf repository from earlier chapters, use it
   instead. Just make sure it contains the Chapter 4 changes.

3. Check that ``git status`` is clean and that ``.env`` was **not** committed (it is in
   ``.gitignore`` since :ref:`ch04_networking_volumes`):

   .. code-block:: bash

      $ git ls-files | grep -c '^\.env$'
      0

.. warning::

   Before your first push to a public repository, look at what you are about to publish:
   ``git ls-files``. Bots scan every public push on GitHub for credentials, and a leaked
   cloud key is typically abused within minutes. Deleting it in a later commit does not
   help, because the history still contains it. The only fix is to **revoke** the key.
