.. _ch01_project_structure:

Python Project Structure
=========================

How you structure a Python project determines how easy it is to test, package, and maintain.
Most tutorials show a flat layout — all files in one directory. This works for scripts but
breaks in surprising ways as projects grow. Production projects use the ``src`` layout.

-----

The ``src`` Layout
------------------

In a **flat layout**, the package lives directly in the project root:

.. code-block:: text

   bookshelf/
     bookshelf/        ← importable package
       __init__.py
       main.py
     tests/
     pyproject.toml

The problem: when you run ``pytest`` from the project root, Python adds the current directory
to ``sys.path``. This means ``import bookshelf`` finds the *raw source directory*, not the
installed package. If the package has broken entry points or missing files in its manifest,
the tests still pass locally — you will not discover the issue until CI or production.

In the **src layout**, the package sits one level deeper:

.. code-block:: text

   bookshelf/
     src/
       bookshelf/      ← only importable after installation
         __init__.py
         main.py
     tests/
     pyproject.toml

Now ``import bookshelf`` only works if the package is explicitly installed (``pip install -e .``).
Tests run against the installed package, not raw source files. Packaging errors are caught
before they reach production.

The BookShelf Project Structure
--------------------------------

Here is the full directory layout you will create in this chapter:

.. code-block:: text

   bookshelf/
   ├── src/
   │   └── bookshelf/
   │       ├── __init__.py
   │       ├── main.py          # FastAPI app factory and startup lifespan
   │       ├── models.py        # Pydantic request/response models
   │       ├── database.py      # SQLite connection and schema init
   │       └── routers/
   │           ├── __init__.py
   │           ├── books.py     # Book CRUD endpoints
   │           └── reviews.py   # Review endpoints
   ├── tests/                   # Populated in Chapter 2
   ├── pyproject.toml           # Project metadata, deps, tool config
   └── README.md

Each layer has a single, clear responsibility. The ``routers/`` sub-package groups endpoints
by resource type. Tests live outside ``src/`` — they are never shipped with the package.

-----

``pyproject.toml`` — The Modern Standard
-----------------------------------------

``pyproject.toml`` replaces ``setup.py``, ``setup.cfg``, ``requirements.txt``, and separate
tool configuration files (``pytest.ini``, ``.flake8``, ``mypy.ini``) with a single file.
Every major Python tool reads it. It is the standard defined in :pep:`518` and :pep:`621`
and is supported by pip, setuptools, uv, hatch, poetry, ruff, mypy, pytest, and more.

Here is the complete ``pyproject.toml`` for the BookShelf API:

.. code-block:: toml
   :caption: :download:`pyproject.toml <support/bookshelf-solution/pyproject.toml>`

   [build-system]
   requires = ["setuptools>=68"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "bookshelf"
   version = "0.1.0"
   description = "A book catalog and review service"
   requires-python = ">=3.11"
   dependencies = [
       "fastapi>=0.111",
       "uvicorn[standard]>=0.30",
   ]

   [project.optional-dependencies]
   dev = [
       "pytest>=8",
       "pytest-cov>=5",
       "httpx>=0.27",
       "ruff>=0.5",
       "mypy>=1.10",
       "pre-commit>=3.7",
   ]

   [tool.setuptools.packages.find]
   where = ["src"]

   [tool.ruff]
   line-length = 88
   target-version = "py311"

   [tool.ruff.lint]
   select = ["E", "F", "I", "UP", "B", "S"]
   ignore = ["S101"]

   [tool.ruff.lint.per-file-ignores]
   "tests/*" = ["S"]

   [tool.mypy]
   strict = true
   python_version = "3.11"

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "--cov=bookshelf --cov-report=term-missing"

The sections are logically grouped into three areas: **build configuration**,
**project metadata and dependencies**, and **tool configuration**. Each is described below.

Build System
^^^^^^^^^^^^

.. code-block:: toml

   [build-system]
   requires = ["setuptools>=68"]
   build-backend = "setuptools.build_meta"

This section is read by pip *before* installing anything. It tells pip which build tool to
download and use when turning your source tree into an installable package.

``requires`` lists the tools pip must install into a temporary build environment. ``build-backend``
is the Python import path to the builder entrypoint. Other valid backends include
``hatchling.build``, ``flit_core.buildapi``, and ``poetry.core.masonry.api`` — they are
interchangeable from pip's perspective.

.. admonition:: Observation:

   If ``[build-system]`` is missing, pip falls back to legacy behaviour and assumes
   setuptools — but emits a deprecation warning. Always include it explicitly.

Project Metadata
^^^^^^^^^^^^^^^^

.. code-block:: toml

   [project]
   name = "bookshelf"
   version = "0.1.0"
   description = "A book catalog and review service"
   requires-python = ">=3.11"
   dependencies = [
       "fastapi>=0.111",
       "uvicorn[standard]>=0.30",
   ]

``name`` must be unique on PyPI if you ever publish the package; for internal-only packages
it can be anything. ``requires-python`` is a hard constraint enforced by pip at install time
— if a user tries to install on Python 3.9, pip will refuse with a clear error rather than
installing and failing mysteriously at runtime.

``dependencies`` lists *runtime* dependencies: packages required for the application to run.
Keep this list minimal. Every entry is a transitive risk — each dependency brings its own
dependencies, its own security surface, and its own upgrade cadence.

**Version specifiers** control which releases pip considers acceptable:

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Specifier
     - Meaning
     - When to use
   * - ``>=0.111``
     - Any version 0.111 or newer
     - Well-maintained libraries where you want security patches automatically
   * - ``>=0.111,<1.0``
     - 0.111 up to (but not including) 1.0
     - Libraries that may introduce breaking changes in major versions
   * - ``==0.111.*``
     - Any 0.111.x patch release
     - When you need predictable minor-version behaviour
   * - ``==0.111.3``
     - Exactly this version
     - Avoid in ``pyproject.toml``; use lock files instead (see below)

.. admonition:: Observation:

   ``uvicorn[standard]`` uses pip's *extras* syntax: install ``uvicorn`` plus the optional
   dependencies listed under its ``[standard]`` group (``httptools``, ``websockets``,
   ``uvloop`` on Linux). Use extras when a library has optional features that require
   additional packages. The square brackets are part of the dependency specifier, not a TOML
   construct.

.. warning::

   Do not pin exact versions (``==x.y.z``) in ``[project] dependencies``. Exact pins make
   it impossible for other packages to share a compatible version and cause unnecessary
   conflicts. Pin exact versions in a *lock file* (``requirements.lock``,
   ``uv.lock``) that is generated from ``pyproject.toml`` and committed separately.
   ``pyproject.toml`` expresses intent; the lock file records the exact resolved state.

Optional Dependencies
"""""""""""""""""""""

.. code-block:: toml

   [project.optional-dependencies]
   dev = [
       "pytest>=8",
       "pytest-cov>=5",
       "httpx>=0.27",
       "ruff>=0.5",
       "mypy>=1.10",
       "pre-commit>=3.7",
   ]

Optional dependency groups are installed on demand using *extras* syntax:

.. code-block:: bash

   $ pip install -e ".[dev]"          # install package + dev tools
   $ pip install -e ".[dev,docs]"     # install package + dev tools + docs tools

The ``dev`` group here contains every tool needed for local development and CI — linting,
type checking, testing, and pre-commit hooks. Keeping them together means a new contributor
can get a fully configured environment with a single command.

You can define multiple groups for different contexts:

.. code-block:: toml

   [project.optional-dependencies]
   dev  = ["pytest>=8", "ruff>=0.5", "mypy>=1.10"]
   docs = ["sphinx>=7", "furo>=2024"]
   ci   = ["pytest-cov>=5", "pytest-xdist>=3"]

Setuptools Package Discovery
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: toml

   [tool.setuptools.packages.find]
   where = ["src"]

Without this, setuptools would scan the project root for Python packages and find nothing
useful — the package lives inside ``src/``. This single line redirects the scan.

The alternative to automatic discovery is an explicit list:

.. code-block:: toml

   [tool.setuptools.packages]
   find = {}  # disabled

   # explicit list:
   [tool.setuptools]
   packages = ["bookshelf", "bookshelf.routers"]

Explicit lists are fragile — you must update them every time you add a sub-package. Let
setuptools discover automatically unless you have a specific reason not to.

Tool Configuration
^^^^^^^^^^^^^^^^^^

The ``[tool.*]`` namespace is reserved for third-party tools. Each tool reads its own
section; tools ignore sections they do not recognise. This is what allows a single file to
configure ruff, mypy, pytest, coverage, and any other tool in the ecosystem.

.. code-block:: toml

   [tool.ruff]
   line-length = 88
   target-version = "py311"

   [tool.mypy]
   strict = true
   python_version = "3.11"

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "--cov=bookshelf --cov-report=term-missing"

These are covered in detail in their respective sections. The key point is that they live
here rather than in ``.flake8``, ``mypy.ini``, ``pytest.ini``, or ``setup.cfg`` — one file,
no hunting across the project root.

.. admonition:: Observation:

   ``target-version = "py311"`` in the ruff config and ``python_version = "3.11"`` in the
   mypy config should match the ``requires-python`` constraint in ``[project]``. If they
   diverge, the linter or type checker may accept syntax that is invalid on the minimum
   supported Python version, or reject syntax that is valid on it. Keep all three in sync
   whenever you bump the minimum Python version.

Editable Install
^^^^^^^^^^^^^^^^

During development, install the package in *editable mode* so changes to source files are
reflected immediately without reinstalling:

.. admonition:: What does ``pip install -e .`` actually do?
   :class: dropdown

   A normal ``pip install`` copies your source files into the virtual environment's
   ``site-packages/`` directory. Editable mode (``-e``) skips the copy and instead writes
   a small ``.pth`` file that points Python directly at your ``src/`` directory:

   .. code-block:: text

      # .venv/lib/python3.11/site-packages/bookshelf.pth
      /path/to/bookshelf/src

   This means ``import bookshelf`` resolves to your live source files. Edit a file, and
   the change is visible on the next import — no reinstall needed.

   **Why is it required at all?** Because of the ``src`` layout. Without an install step,
   Python has no way to find ``src/bookshelf/`` — the ``src/`` directory is not on
   ``sys.path``. Running ``python -m pytest`` or ``python -c "import bookshelf"`` would
   raise ``ModuleNotFoundError``. The editable install is the bridge between the ``src``
   layout's isolation guarantee and a working development environment.

   The ``".[dev]"`` suffix installs the package itself plus everything in
   ``[project.optional-dependencies] dev`` — linters, test tools, and type checkers — in
   one command.

.. code-block:: bash

   $ pip install -e ".[dev]"
   Obtaining file:///path/to/bookshelf
   ...
   Successfully installed bookshelf-0.1.0

Verify the installation works:

.. code-block:: bash

   $ python -c "import bookshelf; print(bookshelf.__version__)"
   0.1.0

-----

**Exercise — Create the Project Structure**

#. Create the directory layout shown above:

   .. code-block:: bash

      $ mkdir -p bookshelf/src/bookshelf/routers bookshelf/tests
      $ touch bookshelf/src/bookshelf/__init__.py
      $ touch bookshelf/src/bookshelf/main.py
      $ touch bookshelf/src/bookshelf/models.py
      $ touch bookshelf/src/bookshelf/database.py
      $ touch bookshelf/src/bookshelf/routers/__init__.py
      $ touch bookshelf/src/bookshelf/routers/books.py
      $ touch bookshelf/src/bookshelf/routers/reviews.py

#. Create ``pyproject.toml`` in the project root with the content shown above.

#. Add a ``__version__`` variable to ``src/bookshelf/__init__.py``:

   .. code-block:: python

      __version__ = "0.1.0"

#. Create a virtual environment and install in editable mode:

   .. code-block:: bash

      $ python -m venv .venv
      $ source .venv/bin/activate   # Linux/macOS
      # .venv\Scripts\activate      # Windows
      $ pip install -e ".[dev]"

#. Verify the import resolves correctly:

   .. code-block:: bash

      $ python -c "import bookshelf; print(bookshelf.__version__)"
      0.1.0

   If this fails with ``ModuleNotFoundError``, check that your virtual environment is active
   and that ``[tool.setuptools.packages.find]`` has ``where = ["src"]`` in ``pyproject.toml``.
