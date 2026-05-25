.. _ch01_precommit:

Pre-commit Hooks
=================

Code quality tools only work if people run them. In a busy team, developers forget. Code
review merges happen with lint errors. Type errors accumulate. The solution is to make
running these checks *automatic*: hook them into the Git commit process so they run whether
the developer remembers or not.

-----

The Problem: Human Forgetfulness
----------------------------------

Consider a team of five developers, each with different habits. One runs ``ruff check``
manually before every commit. Another relies on IDE highlighting. A third often commits
quickly with the intention to "clean up in the next commit." That cleanup commit never comes.

After three months, ``git log`` is full of "fix formatting" and "add missing type hints"
commits that add noise to every release changelog. Code review time is spent on mechanical
issues instead of logic and correctness.

Pre-commit hooks run *before* the commit is recorded. If a hook fails, the commit is aborted.
The developer must fix the issue before the commit goes through. This makes code quality
non-optional at the team level.

-----

The ``pre-commit`` Framework
------------------------------

The ``pre-commit`` tool (not to be confused with Git's native hook mechanism) manages a
collection of hooks sourced from external repositories. It handles downloading hook scripts,
creating isolated environments for each hook, and running them in the correct order.

**Installation:**

.. code-block:: bash

   $ pip install pre-commit

**Configuration** — create ``.pre-commit-config.yaml`` in the project root:

.. code-block:: yaml

   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: v0.5.5
       hooks:
         - id: ruff
           args: [--fix]
         - id: ruff-format

     - repo: https://github.com/pre-commit/pre-commit-hooks
       rev: v4.6.0
       hooks:
         - id: trailing-whitespace
         - id: end-of-file-fixer
         - id: check-yaml
         - id: check-added-large-files
           args: [--maxkb=500]
         - id: check-merge-conflict

**Install the hooks into your local Git repository:**

.. code-block:: bash

   $ pre-commit install
   pre-commit installed at .git/hooks/pre-commit

From this point on, the hooks run automatically on every ``git commit``.

**Run manually against all files (useful on first setup):**

.. code-block:: bash

   $ pre-commit run --all-files

-----

Demo: A Hook Blocking a Bad Commit
------------------------------------

Create a file with formatting problems:

.. code-block:: bash

   $ cat > src/bookshelf/scratch.py << 'EOF'
   import os,sys
   def helper():
     return 42
   EOF

   $ git add src/bookshelf/scratch.py
   $ git commit -m "chore: add scratch file"

The pre-commit hooks fire:

.. code-block:: text

   ruff.....................................................................Failed
   - hook id: ruff
   - exit code: 1
   - files were modified by this hook

   Found 2 errors (2 fixed, 0 remaining).

   ruff-format..............................................................Failed
   - hook id: ruff-format
   - files were modified by this hook

   1 file reformatted.

The commit is blocked. Ruff modified the file on disk. Stage the fixes and commit again:

.. code-block:: bash

   $ git add src/bookshelf/scratch.py
   $ git commit -m "chore: add scratch file"

   ruff.....................................................................Passed
   ruff-format..............................................................Passed
   trailing-whitespace......................................................Passed
   end-of-file-fixer........................................................Passed
   check-yaml...............................................................Passed
   check-added-large-files..................................................Passed
   check-merge-conflict.....................................................Passed
   [main 3f8a2b1] chore: add scratch file
    1 file changed, 3 insertions(+)

.. admonition:: Observation:

   Hooks with ``args: [--fix]`` auto-fix issues and modify files on disk. The commit is still
   blocked (the hook exits non-zero) because Git has already computed the diff for the
   *original* files. You must ``git add`` the modified files and commit again. This is
   intentional — you should always review auto-fixes before committing them.

-----

**Exercise — Set Up Pre-commit**

#. Create ``.pre-commit-config.yaml`` in the project root with the configuration shown above.

#. Install the hooks:

   .. code-block:: bash

      $ pre-commit install

#. Run the hooks against all existing files to ensure everything passes before continuing:

   .. code-block:: bash

      $ pre-commit run --all-files

   Fix any reported issues.

#. Create a Python file with intentional formatting problems — mixed indentation, a
   multi-import statement, and trailing whitespace. Stage it and attempt a commit.
   Observe the hooks fire and modify the file. Stage the fixed version and commit successfully.

#. Verify the ``check-yaml`` hook catches syntax errors. Create a malformed YAML file,
   stage it, and attempt to commit:

   .. code-block:: bash

      $ echo "key: [unclosed" > test.yaml
      $ git add test.yaml
      $ git commit -m "test: bad yaml"

   The hook should block the commit. Delete the file without committing it.

.. admonition:: Observation:

   Pre-commit hooks are installed into ``.git/hooks/`` and are *not* committed to the
   repository. When a new developer clones the repo, they must run ``pre-commit install``
   themselves. The ``.pre-commit-config.yaml`` *is* committed — it defines which hooks to
   use. Add ``pre-commit install`` to your project ``Makefile`` or setup script so developers
   cannot accidentally skip it.
