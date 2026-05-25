.. _ch01_code_quality:

Linters, Formatters & Type Checking
=====================================

In a solo project, inconsistent code style is a minor annoyance. In a team, it creates noise
in every code review: debates about line length, import ordering, and whitespace that delay
feedback on the *actual* logic. Automated tools eliminate this entirely.

More importantly, linters and type checkers catch bugs before code reaches production. A type
mismatch that would cause a ``TypeError`` at runtime is flagged immediately in your editor.
Catching bugs at development time costs almost nothing. Catching them in production costs real
money, user trust, and sleep.

-----

Ruff — Linting and Formatting
-------------------------------

`Ruff <https://docs.astral.sh/ruff/>`_ is an extremely fast Python linter and formatter
written in Rust. It replaces ``flake8``, ``isort``, ``pyupgrade``, and ``black`` with a
single tool that runs in milliseconds even on large codebases.

**Configuration in ``pyproject.toml``:**

.. code-block:: toml

   [tool.ruff]
   line-length = 88
   target-version = "py311"

   [tool.ruff.lint]
   select = ["E", "F", "I", "UP", "B", "S"]
   ignore = ["S101"]   # allow assert statements in tests

   [tool.ruff.lint.per-file-ignores]
   "tests/*" = ["S"]   # disable security rules in test files

Rule sets enabled:

- ``E`` / ``F`` — pycodestyle errors and pyflakes (undefined names, unused imports)
- ``I`` — isort (import ordering and grouping)
- ``UP`` — pyupgrade (modernize syntax for the configured Python version)
- ``B`` — flake8-bugbear (likely bugs and questionable design)
- ``S`` — flake8-bandit (security issues: SQL injection patterns, unsafe calls)

**Running Ruff:**

.. code-block:: bash

   $ ruff check .             # report lint violations
   $ ruff check --fix .       # auto-fix fixable violations
   $ ruff format .            # format all Python files
   $ ruff format --check .    # check formatting without modifying files

**Before and after:**

Take this badly formatted code:

.. code-block:: python

   import os,sys
   from fastapi import FastAPI,HTTPException

   def get_book(id:int)->dict:
     conn=get_connection()
     row=conn.execute('SELECT * FROM books WHERE id=?',(id,)).fetchone()
     if row==None:
       raise HTTPException(status_code=404,detail='Book not found')
     return dict(row)

After ``ruff format . && ruff check --fix .``:

.. code-block:: python

   import os
   import sys

   from fastapi import FastAPI, HTTPException


   def get_book(id: int) -> dict:
       conn = get_connection()
       row = conn.execute("SELECT * FROM books WHERE id=?", (id,)).fetchone()
       if row is None:
           raise HTTPException(status_code=404, detail="Book not found")
       return dict(row)

.. admonition:: Observation:

   Ruff separated the multi-import line, added spaces around operators and after colons,
   switched single quotes to double quotes, changed ``== None`` to ``is None`` (B015 rule),
   and fixed indentation — all automatically. What was 30 seconds of review discussion is
   now zero seconds.

-----

Mypy — Static Type Checking
-----------------------------

Python's type hints are optional annotations that describe what types a function accepts and
returns. Mypy reads these annotations statically — without running the code — and reports
type errors that would otherwise only surface at runtime.

**A bug mypy catches:**

.. code-block:: python

   def format_isbn(isbn: str) -> str:
       return isbn.replace("-", "")

   book_id: int = 42
   result = format_isbn(book_id)   # passing int where str is expected

.. code-block:: bash

   $ mypy src/
   src/bookshelf/routers/books.py:17: error: Argument 1 to "format_isbn" has
   incompatible type "int"; expected "str"  [arg-type]
   Found 1 error in 1 file (checked 6 source files)

Without mypy, this would raise ``AttributeError: 'int' object has no attribute 'replace'``
at runtime — but only on the code path that passes an integer. A code path that might be
hit by 0.1% of requests, silently failing for weeks.

**Configuration in ``pyproject.toml``:**

.. code-block:: toml

   [tool.mypy]
   strict = true
   python_version = "3.11"

``strict`` mode enables: ``--disallow-untyped-defs``, ``--disallow-any-generics``,
``--warn-return-any``, ``--warn-unused-ignores``, and several others. Every function must
have full type annotations — there are no escape hatches.

**Running mypy:**

.. code-block:: bash

   $ mypy src/
   Success: no issues found in 6 source files

.. admonition:: Observation:

   VS Code with the Pylance extension runs pyright (Microsoft's type checker, compatible
   with mypy's type system) in real time as you type — you see inline error highlighting
   without running any command. Install the Python extension and set
   ``"python.analysis.typeCheckingMode": "strict"`` in your VS Code settings for the same
   effect your CI pipeline will enforce.

-----

EditorConfig — Consistent Editor Settings
------------------------------------------

Different developers use different editors. Without explicit configuration, you end up with
mixed indentation (tabs vs spaces), different line endings (``\n`` vs ``\r\n`` on Windows),
or missing newlines at end of file. These cause spurious diffs in every commit and make
``git blame`` harder to read.

``.editorconfig`` is a standard file that tells any editor how to handle these settings.
VS Code, PyCharm, Vim (with plugin), Emacs, and most other editors respect it automatically.

.. code-block:: ini
   :caption: :download:`.editorconfig <support/.editorconfig>`

   root = true

   [*]
   end_of_line = lf
   insert_final_newline = true
   trim_trailing_whitespace = true
   charset = utf-8

   [*.py]
   indent_style = space
   indent_size = 4

   [*.{yaml,yml,toml,json}]
   indent_style = space
   indent_size = 2

   [Makefile]
   indent_style = tab

Create this file in the project root as ``.editorconfig``.

-----

**Exercise — Configure and Run All Quality Tools**

#. Verify ruff is installed and configured by running it on the project source:

   .. code-block:: bash

      $ ruff check src/
      $ ruff format --check src/

   If there are violations, fix them:

   .. code-block:: bash

      $ ruff check --fix src/
      $ ruff format src/

#. Run mypy on the source directory:

   .. code-block:: bash

      $ mypy src/

   Fix all reported errors. Common issues in the BookShelf API:

   - Missing return type annotations — add ``-> ReturnType`` to every function signature
   - ``sqlite3.Row`` typed as ``Any`` — add ``# type: ignore[assignment]`` on specific lines
     where mypy cannot infer the row type from the standard library stubs

#. Create ``.editorconfig`` in the project root with the content shown above.

#. Add type annotations to *all* functions in ``database.py``, ``models.py``, ``routers/books.py``,
   and ``routers/reviews.py``. Run mypy until it reports no errors.

#. Run both tools together to confirm everything passes cleanly:

   .. code-block:: bash

      $ ruff check src/ && ruff format --check src/ && mypy src/
      All checks passed.
      Success: no issues found in 6 source files
