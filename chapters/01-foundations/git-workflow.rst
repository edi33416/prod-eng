.. _ch01_git_workflow:

Git Workflow for Teams
=======================

A Git workflow is a set of conventions about how a team uses branches, merges, and commits.
Without conventions, you get a tangle of long-lived branches, merge conflicts, and a
``git log`` that reads like a stream of consciousness. With conventions, history is clean,
deployments are predictable, and ``git bisect`` actually works.

.. admonition:: Crash Course: Git Essentials
   :class: dropdown

   If you are comfortable with branching, merging, and rebasing, skip this block.

   **Creating and switching branches:**

   .. code-block:: bash

      $ git checkout -b feature/add-reviews   # create and switch
      $ git switch -c feature/add-reviews     # modern equivalent (Git 2.23+)

   **Pushing a branch to the remote:**

   .. code-block:: bash

      $ git push -u origin feature/add-reviews
      # The -u flag sets the upstream tracking branch so future pushes need only: git push

   **Merging vs rebasing:**

   - ``git merge main`` — creates a merge commit, preserves history exactly as it happened
   - ``git rebase main`` — replays your commits on top of main, produces a linear history

   Rebase before merging to avoid tangled history:

   .. code-block:: bash

      $ git fetch origin
      $ git rebase origin/main

   **Undoing things:**

   .. code-block:: bash

      $ git restore <file>       # discard unstaged changes in a file
      $ git reset HEAD <file>    # unstage a staged file
      $ git commit --amend       # rewrite the last commit (before pushing only)

   For a deeper dive, see: `Pro Git Book <https://git-scm.com/book/en/v2>`_

-----

Branch Strategy: Trunk-Based Development
-----------------------------------------

**Trunk-based development** is the branching strategy used by most high-velocity engineering
teams. The rules are simple:

1. There is one canonical branch: ``main`` (the "trunk").
2. All development happens on short-lived **feature branches** branched from ``main``.
3. Feature branches are merged back into ``main`` quickly — ideally within one to two days.
4. ``main`` is *always* in a deployable state.

The alternative — long-lived feature branches (GitFlow, release branches) — leads to painful
merge conflicts and delayed integration. A branch that lives for two weeks accumulates two
weeks of divergence from main. Merging it becomes a multi-hour conflict resolution session.

.. admonition:: Observation:

   "Always deployable" is enforced by CI/CD (Chapter 5). No merge to ``main`` happens without
   automated tests passing. This chapter introduces the workflow; the automation comes later.
   For now, rely on discipline and branch protection rules.

-----

Branch Naming Conventions
--------------------------

Use a consistent prefix to communicate intent at a glance in ``git branch --list`` and PR lists:

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Prefix
     - Purpose
     - Example
   * - ``feature/``
     - New functionality
     - ``feature/search-endpoint``
   * - ``fix/``
     - Bug fix
     - ``fix/isbn-validation``
   * - ``chore/``
     - Maintenance, dependency updates, tooling
     - ``chore/update-pre-commit-hooks``
   * - ``docs/``
     - Documentation only
     - ``docs/api-usage-guide``
   * - ``refactor/``
     - Code restructuring with no behavior change
     - ``refactor/extract-db-layer``

Branch names use lowercase with hyphens. They should describe the change well enough to
understand without opening the PR: ``fix/isbn-validation`` is better than ``fix/bug1``.

.. note::

   **Link branches and commits to issues.** Every non-trivial change should start with an
   issue that describes the problem or requirement before any code is written. This keeps
   intent separate from implementation and gives reviewers context.

   Include the issue number in the branch name and reference it in commit messages:

   .. code-block:: text

      Branch:  fix/42-isbn-validation
      Commit:  fix(books): reject ISBNs that are not 10 or 13 digits

               Issue #42

   When a commit message contains ``Issue #42``, GitHub automatically creates a link between
   the commit (and the PR) and the issue, making the full trail visible: issue → branch → PR
   → commits. Use ``Closes #42`` instead of ``Issue #42`` to also close the issue
   automatically when the PR is merged.

   This habit pays off quickly. Six months later, ``git log`` shows *what* changed;
   the linked issue shows *why*.

-----

Commit Message Conventions
---------------------------

Use the `Conventional Commits <https://www.conventionalcommits.org/>`_ specification:

.. code-block:: text

   <type>(<optional scope>): <short description>

   <optional body — explain WHY if not obvious>

   <optional footer — e.g., Closes #42>

**Types:**

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Type
     - When to use
   * - ``feat``
     - A new feature visible to users or callers
   * - ``fix``
     - A bug fix
   * - ``docs``
     - Documentation only — no code change
   * - ``chore``
     - Maintenance: dependency updates, tooling, build
   * - ``refactor``
     - Code change that neither fixes a bug nor adds a feature
   * - ``test``
     - Adding or updating tests
   * - ``ci``
     - CI/CD pipeline changes

**Good examples:**

.. code-block:: text

   feat(books): add search endpoint with title and author filtering

   fix(reviews): return 404 when book_id not found instead of 500

   chore: update ruff to v0.5.5 and pre-commit hook revisions

   test(books): add integration tests for CRUD endpoints

   refactor(database): extract connection setup into context manager

Why conventional commits? Two reasons:

1. **Automated changelogs.** Tools like ``git-cliff`` parse commit messages to generate
   ``CHANGELOG.md`` and bump version numbers automatically. This is the basis of semantic
   versioning automation used in CI/CD pipelines (Chapter 5).
2. **Scannable history.** ``git log --oneline`` reads like a structured list of decisions,
   not a stream of "fix stuff" and "update" messages.

-----

Maintaining a Changelog
------------------------

A changelog is a human-readable record of notable changes to a project, grouped by release.
It is distinct from ``git log``: a commit log is a diary for developers; a changelog is a
summary for anyone who depends on the project — teammates, API consumers, or operators
deciding whether to upgrade.

The `Keep a Changelog <https://keepachangelog.com/>`_ convention is the de facto standard.
Each version block groups changes under fixed headings:

.. code-block:: markdown

   # Changelog

   ## [Unreleased]

   ### Added
   - Search endpoint: `GET /books/search?q=` filters by title and author

   ### Fixed
   - `POST /books/{id}/reviews` now returns 404 when the book does not exist

   ## [0.2.0] - 2024-11-15

   ### Added
   - `DELETE /books/{id}` endpoint with cascade delete for reviews

   ### Changed
   - Pagination defaults changed: limit raised from 10 to 20

   ## [0.1.0] - 2024-10-01

   ### Added
   - Initial BookShelf API: CRUD for books and reviews, SQLite storage

The ``[Unreleased]`` section accumulates changes since the last release. When you cut a
release, it becomes the new version block and a fresh ``[Unreleased]`` section is opened.

**Headings used:**

- ``Added`` — new features
- ``Changed`` — changes to existing behaviour
- ``Deprecated`` — features that will be removed in a future release
- ``Removed`` — features removed in this release
- ``Fixed`` — bug fixes
- ``Security`` — security fixes (always call these out explicitly)

.. admonition:: Observation:

   Write changelog entries for the *reader*, not the *author*. A good entry answers
   "what changed and why does it affect me?" — not "what did I do?". Compare:

   - **Poor:** ``fix(reviews): handle missing book_id``
   - **Good:** ``POST /books/{id}/reviews now returns 404 when the book does not exist (previously 500)``

   The commit message describes the implementation; the changelog entry describes the impact.

Automated Changelog Generation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the team follows Conventional Commits consistently, the changelog can be generated
automatically from commit history using `git-cliff <https://git-cliff.org/>`_:

.. code-block:: bash

   $ pip install git-cliff       # or: cargo install git-cliff
   $ git cliff --output CHANGELOG.md

``git-cliff`` reads every commit since the last tag, groups them by type (``feat`` →
*Added*, ``fix`` → *Fixed*), and writes a formatted ``CHANGELOG.md``. It is configurable
via a ``cliff.toml`` file and integrates with CI/CD pipelines to run on every release tag
(covered in Chapter 5).

.. note::

   Automated generation works well for libraries and internal services with disciplined
   commit hygiene. For user-facing products, generated entries are often too technical —
   a ``feat: add index on reviews.book_id`` matters to a DBA but not to an API consumer.
   In those cases, use automation as a first draft and edit for clarity before publishing.

   A better approach is to invest in **issue quality**. If every change starts with an
   issue whose title and description are written from the user's perspective — "Searching
   for books by partial author name returns no results" rather than "fix LIKE query" — then
   the issue title is already a good changelog entry. Automation can pull issue titles
   directly via the GitHub API and use them in place of raw commit summaries, producing a
   changelog that reads naturally to end users without any manual editing.

   The issue-linking practice from the previous section pays off here: because commits
   already reference issue numbers, the automated tool has everything it needs to build the
   full picture — user-facing issue title, implementation commits, and linked PR — and can
   include a direct link to the issue in each changelog entry. For users with access to the
   issue tracker, that link opens the full context: the original problem description,
   discussion, and every code change that resolved it.

-----

The Pull Request Workflow
--------------------------

A pull request (PR) is a proposal to merge a feature branch into ``main``. It is the unit
of code review. Every change to ``main`` — from any developer, at any seniority — goes
through a PR. No exceptions.

**Step by step:**

.. code-block:: bash

   # 1. Start from an up-to-date main
   $ git switch main
   $ git pull origin main

   # 2. Create a feature branch
   $ git switch -c feature/search-endpoint

   # 3. Make changes and commit incrementally
   $ git add src/bookshelf/routers/books.py
   $ git commit -m "feat(books): add search endpoint with title and author filtering"

   # 4. Push the branch
   $ git push -u origin feature/search-endpoint
   # Git prints a URL — open it to create the PR on GitHub

   # 5. Review, approve, and merge on GitHub

   # 6. Clean up locally
   $ git switch main
   $ git pull origin main
   $ git branch -d feature/search-endpoint

Protecting ``main``
^^^^^^^^^^^^^^^^^^^^^

On GitHub, branch protection rules enforce the PR workflow and prevent direct pushes to
``main``. Configure them at: **Settings → Branches → Add branch protection rule → ``main``**

Enable:

- ✓ Require a pull request before merging
- ✓ Require at least 1 approval
- ✓ Require status checks to pass before merging (wire in CI checks in Chapter 5)
- ✓ Do not allow bypassing the above settings

.. warning::

   Branch protection only prevents pushing to the *remote* ``main``. You can still commit
   directly to your *local* ``main`` branch — the protection blocks the push. Treat local
   ``main`` as read-only by habit: always work on a feature branch, even for small changes.

-----

Commit Discipline, Squashing & Tags
-------------------------------------

Focused Commits and PRs
^^^^^^^^^^^^^^^^^^^^^^^^

Every commit and every PR should address **exactly one issue**. Not "one issue plus a small
cleanup". Not "two related bugs fixed together". One issue.

This is not pedantry — it is the practice that makes two critical operations possible later:

- **Bisecting regressions.** ``git bisect`` works by binary-searching commits to find the
  first one that introduced a bug. If commits bundle multiple unrelated changes, bisect
  narrows you down to a commit that changed five things at once. You still have to figure out
  which of those five things caused the regression.

- **Reverting safely.** ``git revert <hash>`` creates a new commit that undoes a specific
  change. If a commit fixes a bug *and* refactors a module *and* bumps a dependency, reverting
  it undoes all three — including the refactor and the dependency bump that had nothing to do
  with the problem.

The same principle applies to PRs. A PR that fixes two bugs should be two PRs. A PR that
adds a feature and also "cleans up a few things nearby" should separate the cleanup into its
own PR. Reviewers can evaluate a focused change clearly; they cannot confidently approve a
change that mixes concerns.

.. admonition:: Observation:

   A common objection is that splitting work into many small PRs feels slower. In practice
   the opposite is true: small, focused PRs get reviewed and merged faster, create fewer
   merge conflicts, and are far easier to roll back when something goes wrong. Large PRs
   accumulate review debt — they sit open longer, reviewers defer them, and they are
   eventually merged with less scrutiny than they deserve.

.. admonition:: How to use ``git bisect``
   :class: dropdown

   ``git bisect`` performs a binary search through commit history to find the first commit
   that introduced a bug. Instead of manually checking commits one by one, Git halves the
   search space with each step — finding the culprit in ``log₂(n)`` steps.

   **Start a bisect session:**

   .. code-block:: bash

      $ git bisect start
      $ git bisect bad                  # current commit is broken
      $ git bisect good v0.1.0          # this tag (or any commit hash) was known-good

   Git checks out a commit halfway between the good and bad points. Test whether the bug
   is present, then tell Git the result:

   .. code-block:: bash

      $ python -m pytest tests/unit/test_books.py   # or any manual check
      $ git bisect good    # bug not present — search the later half
      # or
      $ git bisect bad     # bug present — search the earlier half

   Repeat until Git identifies the first bad commit:

   .. code-block:: bash

      a3f1c82 is the first bad commit
      commit a3f1c82
      Author: alice <alice@example.com>
      Date:   Mon Nov 18 14:22:03 2024

          feat(books): add search endpoint with title and author filtering

   **End the session** and return to your original branch:

   .. code-block:: bash

      $ git bisect reset

   **Automating the test step:**

   If you have a test or script that exits ``0`` for good and non-zero for bad, bisect can
   run it automatically — no manual ``good``/``bad`` marking needed:

   .. code-block:: bash

      $ git bisect start
      $ git bisect bad HEAD
      $ git bisect good v0.1.0
      $ git bisect run python -m pytest tests/unit/test_books.py -x

   Git will run the command at each step and mark the result automatically, finishing
   without any further input.

   This only works reliably when commits are small and focused. If the commit that bisect
   identifies changed ten things, you still have to read all ten diffs to find the bug.

Squash and Merge
^^^^^^^^^^^^^^^^^

During development it is normal and useful to commit frequently — "WIP: add search query",
"fix off-by-one", "add missing test". These intermediate commits are useful locally but they
add noise to ``main``'s history.

The solution is **squash merging**: when a PR is merged, all of its commits are collapsed
into a single commit on ``main``. The result is a ``main`` history where each commit
corresponds to exactly one issue and one PR — clean, linear, and easy to read.

On GitHub, configure this in **Settings → General → Pull Requests**:

- ✓ Allow squash merging
- ✓ Allow rebase merging
- ✗ Disable merge commits

Both squash and rebase merging produce a clean, linear history without merge commits.
Squash collapses the entire PR into one commit; rebase replays each commit individually.
For most teams, squash merging is preferable because it enforces the one-commit-per-issue
invariant regardless of how many intermediate "WIP" commits were made on the branch.
Rebase merging is a reasonable choice when the branch commits are already clean and
meaningful on their own.

.. code-block:: bash

   # What main looks like with squash merging:
   $ git log --oneline main
   a3f1c82 feat(books): add search endpoint with title and author filtering  (Issue #12)
   9e2b447 fix(reviews): return 404 when book does not exist  (Issue #9)
   d84a019 chore: update pre-commit hook revisions  (Issue #7)
   1c30f11 feat: initial BookShelf API implementation

Every line is one PR, one issue, one logical change. ``git revert a3f1c82`` cleanly undoes
the search endpoint and nothing else.

.. warning::

   Do not mix merge commits with squash or rebase merging on the same repository.
   Merge commits create non-linear history that undermines ``git bisect`` and makes
   ``git log`` harder to read. Pick either squash or rebase as your team's standard,
   disable merge commits, and enforce it.

Tags and Releases
^^^^^^^^^^^^^^^^^^

A **tag** is a named pointer to a specific commit. Tags mark release points — they are how
you answer "what was running in production on November 15th?" without digging through commit
hashes.

Use **annotated tags** for releases. Unlike lightweight tags (just a pointer), annotated
tags store a message, a timestamp, and the tagger's identity, and are included in
``git describe`` output.

.. code-block:: bash

   # Create an annotated release tag
   $ git tag -a v0.2.0 -m "Release v0.2.0"
   $ git push origin v0.2.0

   # List all tags
   $ git tag --list
   v0.1.0
   v0.2.0

   # See what changed since the last tag
   $ git log v0.1.0..v0.2.0 --oneline
   a3f1c82 feat(books): add search endpoint with title and author filtering
   9e2b447 fix(reviews): return 404 when book does not exist

Follow **Semantic Versioning** (`semver.org <https://semver.org/>`_) for tag names:

.. list-table::
   :widths: 15 25 60
   :header-rows: 1

   * - Format
     - Example
     - When to increment
   * - ``vMAJOR``
     - ``v2.0.0``
     - Breaking change — existing callers must update their code
   * - ``vMAJOR.MINOR``
     - ``v0.2.0``
     - New feature, backwards-compatible
   * - ``vMAJOR.MINOR.PATCH``
     - ``v0.2.1``
     - Bug fix, backwards-compatible

With Conventional Commits and squash merging in place, the version bump and tag creation can
be automated in CI/CD: a ``feat`` commit triggers a minor bump; a ``fix`` commit triggers a
patch bump; a commit with ``BREAKING CHANGE:`` in the footer triggers a major bump. This is
covered in Chapter 5.

.. admonition:: Observation:

   Tags are what tie everything together: a tag points to a commit, the commit references
   an issue, the issue links back to the PR and the full discussion. A release becomes a
   fully traceable artifact — from the version number all the way back to the original
   requirement that motivated the change.

-----

**Exercise — Feature Branch Workflow**

#. Ensure you are on ``main`` and up to date. If you have not yet initialized a remote
   repository, do so now:

   .. code-block:: bash

      $ git init
      $ git add .
      $ git commit -m "feat: initial BookShelf API implementation"
      $ git remote add origin https://github.com/<your-username>/bookshelf.git
      $ git push -u origin main

#. Create a feature branch:

   .. code-block:: bash

      $ git switch -c feature/search-endpoint

#. The search endpoint is already implemented in ``routers/books.py`` from the previous
   section. Verify it is present, then stage and commit it:

   .. code-block:: bash

      $ git add src/bookshelf/routers/books.py
      $ git commit -m "feat(books): add search endpoint with title and author filtering"

#. Push the branch and open a pull request on GitHub:

   .. code-block:: bash

      $ git push -u origin feature/search-endpoint

   Open the URL that Git prints. Write a short PR description explaining what the endpoint
   does and how to test it manually (e.g., a ``curl`` example).

#. Review and merge the PR on GitHub (self-approve for this exercise).

#. Pull the updated ``main`` and clean up the local branch:

   .. code-block:: bash

      $ git switch main && git pull origin main
      $ git branch -d feature/search-endpoint

#. Verify the branch is gone locally and the search endpoint commit is visible in ``git log``.
