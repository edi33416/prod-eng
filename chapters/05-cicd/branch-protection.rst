.. _ch05_branch_protection:

Branch Protection and Quality Gates
====================================

.. admonition:: Crash Course: Git Branching Strategies
   :class: dropdown

   :ref:`ch01_git_workflow` introduced **trunk-based development**: one long-lived
   branch (``main``), short-lived feature branches merged within a day or two, and
   ``main`` always deployable. It is the model this course uses. Two others are
   common in the wild:

   **Feature branches (GitHub flow).** Trunk-based with pull requests: every change gets
   a branch and a PR, CI runs on the PR, and a merge to ``main`` deploys. With
   short-lived branches, this is trunk-based development as most teams practise it on
   GitHub.

   **GitFlow.** Two long-lived branches, ``main`` (released code) and ``develop``
   (integration), plus ``feature/*``, ``release/*`` and ``hotfix/*`` branches with
   rules for which merges into which. It was designed for software shipped in versioned
   releases (desktop apps, libraries with several supported versions). For a
   continuously deployed web service it mostly adds merge overhead and delays
   integration, so its own author now recommends simpler flows for such projects.

   **Merge, rebase, or squash?** Given ``main`` and a two-commit feature branch that
   diverged:

   .. code-block:: bash

      # merge commit (git merge --no-ff): history keeps the branch shape
      $ git log --oneline --graph
      *   ccaa532 Merge branch 'feat/top-books'
      |\
      | * d111593 test: cover top books ordering
      | * b0d6fb1 feat: add top books query
      * | f8da7a7 fix: validate ISBN digits
      |/
      * 23dc6c9 feat: add books endpoint

      # rebase + fast-forward: linear, feature commits replayed on top of main
      $ git log --oneline --graph
      * 30b4bfb test: cover top books ordering
      * 1a72780 feat: add top books query
      * f8da7a7 fix: validate ISBN digits
      * 23dc6c9 feat: add books endpoint

      # squash merge: the whole PR becomes one commit on main
      $ git log --oneline --graph
      * 13ef59a feat: top books endpoint (#12)
      * f8da7a7 fix: validate ISBN digits
      * 23dc6c9 feat: add books endpoint

   Note that rebasing **rewrote** the feature commits: ``b0d6fb1`` became ``1a72780``.
   Never rebase commits other people have already pulled.

   Squash merging (the default recommended in :ref:`ch01_git_workflow`) gives a linear
   ``main`` where **every commit is a PR that passed CI**. ``git bisect`` and reverts
   operate on whole, tested changes. The cost is losing the individual commits on
   ``main``. They remain visible in the PR.

   For a deeper dive, see: `Trunk Based Development <https://trunkbaseddevelopment.com/>`_
   and `Pro Git, Branching <https://git-scm.com/book/en/v2/Git-Branching-Rebasing>`_

-----

Green CI Is Not a Gate Until It Blocks Merging
-----------------------------------------------

You now have a pipeline that runs on every pull request. Nothing stops anyone from
ignoring it. GitHub will happily merge a pull request with a red ✗, and anyone with
write access can push straight to ``main`` without opening a PR at all. The checks run
*after* the fact, and CD deploys whatever landed, as long as CI passed on it.

A typical failure looks like this: a five-minute fix pushed directly to ``main`` at
18:00 on a Friday, because "it's one line". CI goes red at 18:04, and nobody is watching
anymore. Monday's first deployment ships it.

:ref:`ch01_git_workflow` configured a protection rule for ``main`` that requires pull
requests and an approval, and promised to wire in the CI checks "in Chapter 5". This
page keeps that promise. Once a check is **required**, the merge button is disabled
until it passes.

-----

Configuring the Rule
---------------------

GitHub has two mechanisms: classic **branch protection rules** (Settings → Branches) and
the newer **rulesets** (Settings → Rules → Rulesets). Rulesets can target many branches
at once, can be applied organisation-wide, and can be switched to *evaluate* mode for a
dry run. For a single repository the options are the same. This page uses the classic
rule, which is what :ref:`ch01_git_workflow` set up.

**Settings → Branches → Edit** (or **Add classic branch protection rule**), branch name
pattern ``main``:

.. code-block:: text

   Protect matching branches
   ☑ Require a pull request before merging
       ☑ Require approvals                                    Required: 1
       ☑ Dismiss stale pull request approvals when new commits are pushed
   ☑ Require status checks to pass before merging
       ☑ Require branches to be up to date before merging
       Status checks that are required:
         [ lint ]  [ test ]  [ test-pg ]  [ build ]           (GitHub Actions)
   ☑ Require conversation resolution before merging
   ☑ Require linear history
   ☑ Do not allow bypassing the above settings
   ☐ Allow force pushes
   ☐ Allow deletions

What each setting buys you:

**Require a pull request / approvals**
   No direct pushes to ``main``. Every change is reviewed by someone other than its
   author.

**Dismiss stale approvals**
   Without it, a reviewer approves a harmless change, the author then pushes a
   completely different commit, and the old approval still counts.

**Require status checks**
   The four CI jobs must report success **on the PR's latest commit** before the merge
   button is enabled. The search box only offers checks that have run in this
   repository in the past week, so push the full pipeline at least once first.

**Require branches to be up to date**
   CI must have run on the PR **combined with the current** ``main``. Two PRs that each
   pass on their own can break when combined. One renames a function, the other adds a
   new call to the old name. With this setting, the second PR must be updated and
   re-tested after the first one merges. On a busy repository this becomes a queue of
   "update branch, wait for CI" clicks. GitHub's **merge queue** automates it.

**Require linear history**
   Only squash or rebase merges, no merge commits. Matches the squash workflow from
   Chapter 1.

**Do not allow bypassing**
   By default, administrators (you, in your own repository) can merge despite failing
   checks. With this setting, the rules apply to everyone. That is the point: in an
   incident at 3 a.m., "just this once" is exactly when a broken change slips through.

.. warning::

   **GitHub never lets the author of a PR approve it.** In a personal repository where
   you are the only collaborator, ``Required approvals: 1`` makes every PR
   unmergeable, unless you allow bypassing, which defeats the exercise. For the lab,
   **pair up**: add a classmate as a collaborator (Settings → Collaborators) and review
   each other's PRs. If you must work alone, set required approvals to 0 and keep the
   status checks required. The CI gate is the part this chapter is about.

-----

Status Check Names
-------------------

A required check is identified by its **name** as reported by the job, and in GitHub
Actions that is the job's ``name:``. The workflows in this chapter set ``name:``
explicitly (``name: lint``, ``name: test``) for that reason. Three ways to break a
required check by accident:

**Renaming a job.**
   Rename ``test`` to ``tests`` and the rule still waits for ``test``. Every PR shows:

   .. code-block:: text

      test       Expected — Waiting for status to be reported       Required

   and can never be merged. Update the rule in the same change that renames the job.

**Adding a matrix.**
   With ``strategy.matrix.python-version``, the ``test`` job reports as
   ``test (3.11)``, ``test (3.12)``, … and the check named ``test`` never arrives.
   Either require each matrix entry, or add a small final job that ``needs`` the matrix
   and require that one.

**Path filters on the workflow.**
   If ``ci.yml`` has ``paths-ignore: ["**.md"]``, a docs-only PR does not trigger the
   workflow at all, the required checks never report, and the PR is stuck. (A job that
   **runs** but is skipped through an ``if:`` reports *Skipped*, which counts as
   passing.) Avoid workflow-level path filters on workflows with required checks.

-----

The Workflow End to End
------------------------

With protection in place, every change follows the same path:

.. code-block:: text

   git switch -c fix/search-pagination
   ... edit, make lint, make coverage ...
   git push -u origin fix/search-pagination
           │
           ▼
   Open PR ──▶ CI on the merge result: lint, test, test-pg, build
           │                        │
           │            red: push fixes to the same branch, CI re-runs
           ▼
   Reviewer approves (approval dismissed if new commits arrive)
           │
           ▼
   Squash and merge (enabled only when all required checks are green)
           │
           ▼
   push to main ──▶ CI ──▶ CD: build-and-push ──▶ staging ──▶ ⏸ approval ──▶ production

The bottom of a PR with a failing check looks like this:

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ ✗ Some checks were not successful                                        │
   │   1 failing, 3 successful checks                                         │
   │                                                                          │
   │   ✗ CI / test (pull_request)      Failing after 34s   Required  Details  │
   │   ✓ CI / lint (pull_request)      Successful in 22s   Required  Details  │
   │   ✓ CI / test-pg (pull_request)   Successful in 36s   Required  Details  │
   │   ⊘ CI / build (pull_request)     Skipped             Required           │
   │                                                                          │
   │ ✗ Merging is blocked                                                     │
   │   The base branch requires all required status checks to pass.           │
   │                                                                          │
   │   [ Squash and merge ▾ ]  (disabled)                                     │
   └──────────────────────────────────────────────────────────────────────────┘

Note that ``build`` shows *Skipped* because ``test``, one of the jobs it ``needs``,
failed. The skip counts as passing, but the failed ``test`` still blocks the merge on
its own.

.. admonition:: Observation:

   Branch protection is enforced by **GitHub's server**, not by anyone's discipline.
   That is the difference from the pre-commit hooks of Chapter 1 and the ``make all`` of
   Chapter 3, which were the tools that let 19 lint errors pile up
   (:ref:`ch05_full_pipeline`). Hooks and Makefiles give fast local feedback. The server
   enforces the rule.

-----

Beyond the Basics
------------------

**CODEOWNERS.** A ``.github/CODEOWNERS`` file maps paths to people or teams, who are
then automatically requested as reviewers. With **Require review from Code Owners**
enabled, a change to ``.github/workflows/`` can require approval from whoever owns the
pipeline:

.. code-block:: text

   # .github/CODEOWNERS
   /.github/workflows/   @<you>
   /src/bookshelf/database.py   @<you> @<classmate>

This matters because a pull request can modify the workflow that tests it. Protecting
``main`` is only meaningful if changes to the pipeline itself get a careful review.

**Protecting environments, not just branches.** The ``production`` environment from
:ref:`ch05_secrets_environments` should allow deployments from ``main`` only. Together
with branch protection, that means production only ever runs code that was reviewed,
passed CI, and was explicitly approved for deployment.

-----

**Exercise — Make CI a Required Gate**

#. Make sure the full CI workflow has run at least once on ``main`` so that GitHub knows
   the check names. Then configure the protection rule for ``main`` as shown above:
   require a PR, require the ``lint``, ``test``, ``test-pg`` and ``build`` checks,
   require branches to be up to date, require linear history, and do not allow
   bypassing. Set required approvals to 1 if you work in a pair (add your partner as a
   collaborator), or 0 if you work alone.

#. Try to push a commit directly to ``main``:

   .. code-block:: bash

      $ git switch main
      $ git commit --allow-empty -m "test: direct push"
      $ git push

   Read the error message. Then reset your local ``main`` to match the remote:
   ``git reset --hard origin/main``.

#. Create a branch, break a test (for example, change an expected status code in an
   integration test), push it and open a PR. Observe:

   - which checks run, which fail, and what ``build`` shows
   - that the merge button is disabled, and the exact message GitHub shows

#. Push a fix to the same branch. Confirm that CI runs again automatically and the
   checks turn green. If you work in a pair, have your partner approve; then push one
   more trivial commit and observe that the approval is dismissed.

#. Merge with **Squash and merge**. Follow what happens next: CI on ``main``, then CD,
   then the production approval. Look at ``git log --oneline`` on ``main``: how many
   commits did your PR add?

#. On a scratch branch, rename the ``test`` job's ``name:`` to ``tests`` and open a PR.
   What does the checks box show? Close the PR without merging and explain how you would
   rename a required job safely.
