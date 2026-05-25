.. _ch01_deps:

Dependencies & Virtual Environments
=====================================

Every Python project needs isolated dependencies. Installing packages globally pollutes your
system Python and causes version conflicts across projects. Virtual environments solve this
for development. In production, containers (Chapter 4) go one step further by isolating the
entire runtime — not just the packages.

.. admonition:: Crash Course: Python Virtual Environments
   :class: dropdown

   A virtual environment is an isolated Python installation with its own ``site-packages``
   directory. It does not copy the Python interpreter itself — it symlinks to the system
   Python and provides a separate space for packages.

   **Create and activate:**

   .. code-block:: bash

      $ python -m venv .venv            # create the venv in .venv/
      $ source .venv/bin/activate       # Linux/macOS
      $ .venv\Scripts\activate          # Windows (PowerShell)

   **Verify isolation:**

   .. code-block:: bash

      $ which python
      /path/to/project/.venv/bin/python

      $ pip list
      Package    Version
      ---------- -------
      pip        24.0

   Only ``pip`` is present — no globally installed packages bleed in.

   **Deactivate:**

   .. code-block:: bash

      $ deactivate

   **Common pitfalls:**

   - Forgetting to activate the venv installs packages globally. Always check ``which python``.
   - Never commit the ``.venv/`` directory — add it to ``.gitignore``.
   - Moving the project directory breaks the venv symlinks. Just recreate it: ``python -m venv .venv``.

   For a deeper dive, see: `Python venv documentation <https://docs.python.org/3/library/venv.html>`_

-----

Installing Dependencies
------------------------

With the virtual environment active, install all dependencies in one command:

.. code-block:: bash

   $ pip install -e ".[dev]"

This installs:

- ``fastapi`` and ``uvicorn`` (runtime dependencies from ``[project].dependencies``)
- ``pytest``, ``ruff``, ``mypy``, ``pre-commit``, ``httpx`` (dev dependencies from ``[project.optional-dependencies].dev``)
- The ``bookshelf`` package itself in editable mode

.. admonition:: Observation:

   In production (inside a Docker container), only runtime dependencies are installed:
   ``pip install .`` — no ``[dev]`` extras. This keeps the production image lean and avoids
   shipping test and linting tools to users. You will implement this distinction in Chapter 4.

-----

Pinning Dependencies
---------------------

The ``pyproject.toml`` specifies *minimum* versions (e.g., ``fastapi>=0.111``). This is
correct for expressing compatibility — your code works with any ``fastapi`` at or above that
version.

The problem: ``pip install`` picks the *latest* compatible version at install time. Today's
install uses ``fastapi==0.111.0``. Three months from now, a new teammate doing a fresh install
might get ``fastapi==0.115.0``. If a dependency introduced a breaking change, your service
might fail in production — and you would not catch it until it did.

A **lockfile** solves this: it pins the exact version of every package (including transitive
dependencies) so every install produces an identical environment.

pip-tools
^^^^^^^^^^

``pip-tools`` generates lockfiles from ``pyproject.toml``:

.. code-block:: bash

   $ pip install pip-tools
   $ pip-compile --output-file=requirements.lock pyproject.toml
   $ pip-compile --extra=dev --output-file=requirements-dev.lock pyproject.toml

   # Apply the lockfile (replaces pip install):
   $ pip-sync requirements-dev.lock

uv (Recommended)
^^^^^^^^^^^^^^^^^

``uv`` is a modern, extremely fast package manager (written in Rust) that handles virtual
environments, dependency resolution, and lockfiles in one tool:

.. code-block:: bash

   $ pip install uv
   $ uv sync              # create venv + install all deps from lockfile
   $ uv sync --no-dev     # runtime deps only (for production containers)
   $ uv lock              # regenerate uv.lock after changing pyproject.toml

   # Run a command without activating the venv:
   $ uv run uvicorn bookshelf.main:app --reload

``uv`` is significantly faster than pip for large dependency trees and is the recommended
choice for new projects. This course uses ``pip`` for commands to stay tool-agnostic,
but the support files include a ``uv.lock`` for reference.

-----

Dev vs Production Dependencies
--------------------------------

Keep development tooling out of the production deployment. The ``pyproject.toml`` structure
separates them explicitly:

.. code-block:: toml

   [project]
   dependencies = [
       "fastapi>=0.111",         # needed to run the API
       "uvicorn[standard]>=0.30",
   ]

   [project.optional-dependencies]
   dev = [
       "pytest>=8",              # only needed during development
       "pytest-cov>=5",
       "httpx>=0.27",
       "ruff>=0.5",
       "mypy>=1.10",
       "pre-commit>=3.7",
   ]

Development install:

.. code-block:: bash

   $ pip install -e ".[dev]"   # everything

Production install (in your Dockerfile, Chapter 4):

.. code-block:: bash

   $ pip install .             # runtime deps only

-----

**Exercise — Install Dependencies and Generate a Lockfile**

#. With your virtual environment active, install all dependencies:

   .. code-block:: bash

      $ pip install -e ".[dev]"

   Spot-check the key packages:

   .. code-block:: bash

      $ python -c "import fastapi; print(fastapi.__version__)"
      0.111.x

      $ ruff --version
      ruff 0.5.x

      $ mypy --version
      mypy 1.10.x

#. Generate a lockfile:

   .. code-block:: bash

      $ pip install pip-tools
      $ pip-compile --output-file=requirements.lock pyproject.toml
      $ pip-compile --extra=dev --output-file=requirements-dev.lock pyproject.toml

   Open ``requirements.lock`` and inspect it. Notice that it pins every package —
   including packages that ``fastapi`` depends on, such as ``pydantic``, ``starlette``,
   and ``anyio``. These are not listed in your ``pyproject.toml`` but are locked to prevent
   unexpected updates.

#. Add the following to ``.gitignore`` (create the file in the project root):

   .. code-block:: text

      .venv/
      __pycache__/
      *.pyc
      *.db
      .mypy_cache/
      .ruff_cache/
      .pytest_cache/

   Commit ``requirements.lock`` and ``requirements-dev.lock`` — these belong in version
   control so every developer and CI job uses identical package versions.
