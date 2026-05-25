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
Every major Python tool reads it.

Here is the complete ``pyproject.toml`` for the BookShelf API:

.. code-block:: toml

   [build-system]
   requires = ["setuptools>=68"]
   build-backend = "setuptools.backends.legacy:build"

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

Key sections:

- ``[build-system]`` — tells pip how to build the package
- ``[project]`` — package metadata: name, version, Python constraint, runtime dependencies
- ``[project.optional-dependencies]`` — dev tools installed with ``pip install -e ".[dev]"``
- ``[tool.setuptools.packages.find]`` — tells setuptools to look for packages inside ``src/``
- ``[tool.ruff]``, ``[tool.mypy]``, ``[tool.pytest.ini_options]`` — tool configuration (no extra files needed)

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
