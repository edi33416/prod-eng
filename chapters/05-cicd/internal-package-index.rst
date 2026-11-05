.. _ch05_internal_package_index:

Installing From an Internal Package Index
==========================================

.. note::

   This page uses ``support/pypi-mirror/``: a Compose file for
   `pypiserver <https://github.com/pypiserver/pypiserver>`_ and a ``populate.sh`` script
   that fills it from a lockfile. It runs entirely on your machine. You need about 80 MB
   of disk space for the downloaded packages.

-----

Every Build Depends on a Stranger's Server
-------------------------------------------

Each ``pip install`` in the pipeline downloads code from PyPI. That code was uploaded by
people you have never met, and it stays available only as long as they and PyPI keep
it there. Two kinds of incident follow from that:

**A package disappears.** In March 2016, after a naming dispute, a developer unpublished
all 250 of his packages from npm. One of them, ``left-pad``, was eleven lines of code
that padded a string. It was also a transitive dependency of Babel and React, so builds
failed across the industry within hours, at companies that had never heard of it. npm
restored the package and changed its rules. PyPI still lets maintainers **delete**
releases, and a deleted version cannot be uploaded again.

**A package is replaced by something malicious.** In December 2024, versions 8.3.41 and
8.3.42 of ``ultralytics``, a computer vision library with millions of monthly downloads,
appeared on PyPI with a cryptocurrency miner inside. The attacker had not touched the
source repository. They had exploited a script injection in the project's own GitHub
Actions workflow, the class of bug from :ref:`ch05_secrets_environments`, to make the
legitimate release pipeline publish poisoned builds. Anyone who installed
``ultralytics`` without a pinned version in the following hours got the miner.

The lockfiles from Chapter 4 and :ref:`ch05_full_pipeline` already protect BookShelf
against part of this: a pinned ``fastapi==0.162.0`` will not silently become a
compromised ``0.162.1``. But a lockfile cannot bring back a deleted file, and it only
covers what is *in* it. Not everything pip installs is:

- ``pip install -e .`` installs the **build backend** from ``[build-system]`` in
  ``pyproject.toml``: ``setuptools>=68``, unpinned. Every editable install in CI fetches
  the newest setuptools release.
- Ad-hoc installs in scripts and workflows (``pip install pip-tools``,
  ``pip install twine``) pick whatever is newest.
- A developer who adds a dependency runs ``pip-compile`` and gets whatever PyPI serves
  **at that moment**, including a release published five minutes earlier.

-----

The Internal Index
-------------------

The fix is to stop installing from PyPI directly. Every pip in the organisation, on
laptops, in CI and in Docker builds, installs from an **internal package index** that
contains only packages someone deliberately put there:

.. code-block:: text

                 ┌──────────────── curation (reviewed, deliberate) ───────────────┐
   pypi.org ──▶  │ populate.sh  requirements-dev.lock ──▶ pip download ──▶ wheels │
                 └──────────────────────────────────────────────┬─────────────────┘
                                                                ▼
                                                 ┌──────────────────────────────┐
                                                 │ internal index (pypiserver)  │
                                                 │ --disable-fallback           │
                                                 └──────┬──────────┬───────┬────┘
                                                        ▼          ▼       ▼
                                                     laptops     CI    docker build

What that buys you:

- **Availability.** A package deleted from PyPI, a PyPI outage, or a rate limit no
  longer breaks your builds. The files you depend on are on your own server.
- **Control.** A package or version that is not in the index **cannot be installed**,
  by anyone, by accident. A compromised release on PyPI does not reach you unless
  someone copies it in. That copy step is where review happens.
- **One place to look.** "Which packages does the company run?" has an answer: the
  contents of the index. Vulnerability scanning (Chapter 10) has one place to scan.

The cost is the curation step. Adding or upgrading a dependency now takes one more
deliberate action. That friction is the point of the exercise.

-----

Run the Index
--------------

``support/pypi-mirror/docker-compose.yml``:

.. code-block:: yaml

   # Internal Python package index: serves only the wheels in ./packages.
   #   ./populate.sh ../bookshelf-ch5-solution/requirements-dev.lock
   #   docker compose up -d
   #   pip install --index-url http://localhost:8080/simple/ ...
   name: pypi-mirror

   services:
     pypi:
       image: pypiserver/pypiserver:v2.4.2
       # --disable-fallback: a package that is not in ./packages is an error,
       #   not a silent redirect to pypi.org (the default).
       # No password file (-P): uploads are refused. The index is populated
       #   only through populate.sh, after review.
       command: run --disable-fallback /data/packages
       ports:
         - "127.0.0.1:8080:8080"
       volumes:
         - ./packages:/data/packages:ro
       restart: unless-stopped

pypiserver serves a directory of wheel files using the same "simple" protocol as PyPI,
so pip needs no plugins. Three settings make it an index you can trust:

``--disable-fallback``
   By default, pypiserver answers a request for a package it does not have by
   **redirecting pip to pypi.org**. pip follows the redirect, and the unvetted package
   is installed as if the internal index did not exist. This flag turns a missing
   package into an error.

No ``-P`` password file
   pypiserver only accepts uploads from authenticated users. With no password file
   there are none, so the index is read-only over HTTP. The ``:ro`` mount makes the
   directory read-only inside the container too.

``127.0.0.1:8080``
   Reachable from your machine only. A real internal index sits on the company network
   behind HTTPS (Chapter 7 puts services behind Nginx with TLS).

-----

Populate It From the Lockfile
------------------------------

``populate.sh`` downloads **exactly the wheels the lockfile pins**, for the platforms you
deploy to:

.. code-block:: bash

   for arch in x86_64 aarch64; do
     pip download --quiet --disable-pip-version-check \
       --requirement /in/requirements.lock --dest /packages \
       --only-binary=:all: --implementation cp --python-version 3.12 \
       --abi cp312 --abi abi3 --abi none \
       --platform "manylinux_2_28_$arch" --platform "manylinux_2_17_$arch" \
       --platform "manylinux2014_$arch" --platform any
   done
   # Build backend for "pip install -e ." (see [build-system] in pyproject.toml).
   pip download --quiet --disable-pip-version-check \
     --only-binary=:all: --dest /packages "setuptools==84.2.1"

The details matter:

- **Target platforms, not your laptop's.** ``pip download`` normally fetches wheels for
  the machine it runs on. A Mac would download macOS wheels, which are useless to a
  Linux CI runner. ``--platform``, ``--python-version``, ``--implementation`` and
  ``--abi`` ask for the wheels a **Linux, CPython 3.12** machine would install. The loop
  runs once per CPU architecture: ``x86_64`` for GitHub's runners and most servers,
  ``aarch64`` for Apple Silicon (Docker Desktop runs Linux ``arm64`` containers) and
  ARM servers. Pure-Python wheels (``py3-none-any``) are shared by both.
- **Wheels only.** ``--only-binary=:all:`` refuses source distributions. Installing an
  sdist **runs its ``setup.py``**, arbitrary code from the internet, on the machine
  doing the install. Wheels are unpacked, not executed.
- **The build backend is pinned here**, even though ``pyproject.toml`` says
  ``setuptools>=68``. The index contains exactly one setuptools, so that is the one
  every editable install gets.
- The script runs ``pip`` inside ``python:3.12.16-slim-trixie``, the base of the
  production image, so the result does not depend on the Python installed on your
  machine.

Run it and start the server:

.. code-block:: bash

   $ cd support/pypi-mirror
   $ ./populate.sh ../bookshelf-ch5-solution/requirements-dev.lock
   55 wheels in /home/student/prod-eng/support/pypi-mirror/packages
   $ du -sh packages
    74M    packages
   $ ls packages | grep -E 'psycopg_binary|setuptools'
   psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
   psycopg_binary-3.3.6-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
   setuptools-84.2.1-py3-none-any.whl

   $ docker compose up -d
    ✔ Container pypi-mirror-pypi-1  Started

``packages/`` is in ``.gitignore``. It can be rebuilt from the lockfiles at any time, and
74 MB of wheels does not belong in Git.

-----

Point pip at It
----------------

pip reads its index from, in decreasing order of precedence:

.. list-table::
   :header-rows: 1
   :widths: 30 42 28

   * - Where
     - Example
     - Use for
   * - Command-line option
     - ``pip install --index-url http://localhost:8080/simple/ ...``
     - One-off commands
   * - Environment variable
     - ``export PIP_INDEX_URL=http://localhost:8080/simple/``
     - CI jobs, Docker builds
   * - Config file
     - ``pip config --user set global.index-url ...``
     - Developer machines

Every pip option has an environment variable: upper-case it and prefix ``PIP_``. The
config file version persists for your user:

.. code-block:: bash

   $ pip config --user set global.index-url http://localhost:8080/simple/
   Writing to /home/student/.config/pip/pip.conf
   $ cat ~/.config/pip/pip.conf
   [global]
   index-url = http://localhost:8080/simple/
   $ pip config list
   global.index-url='http://localhost:8080/simple/'

Now install BookShelf in a fresh virtual environment:

.. code-block:: bash

   $ python3.12 -m venv /tmp/mirror-venv && . /tmp/mirror-venv/bin/activate
   $ pip install -r requirements-dev.lock
   Looking in indexes: http://localhost:8080/simple/
   Collecting annotated-doc==0.0.5 (from -r requirements-dev.lock (line 7))
     Downloading http://localhost:8080/packages/annotated_doc-0.0.5-py3-none-any.whl (5.3 kB)
   ...
   Successfully installed annotated-doc-0.0.5 ... fastapi-0.162.0 ... ruff-0.17.3 ...
   $ pip install --no-deps -e .
   ...
   Successfully installed bookshelf-0.5.0
   $ pytest -q
   ...
   ======================== 80 passed, 1 warning in 1.11s =========================

``Looking in indexes:`` is the line to check: it shows which index pip actually uses.
Every ``Downloading`` URL points at ``localhost:8080``.

.. note::

   The examples need Python 3.12 on Linux, because the index only holds wheels for that
   target. On macOS, run them inside a container on the host network:
   ``docker run --rm -it --network host -v "$PWD":/w -w /w python:3.12.16-slim-trixie bash``.
   (Host networking needs Docker Desktop 4.34 or later on macOS and Windows.)

-----

Watch It Say No
----------------

An index that refuses nothing protects nothing. Try a package that is not in the lockfile:

.. code-block:: bash

   $ pip install requests
   Looking in indexes: http://localhost:8080/simple/
   ERROR: Could not find a version that satisfies the requirement requests (from versions: none)
   ERROR: No matching distribution found for requests

And a version that was never mirrored:

.. code-block:: bash

   $ pip install "fastapi==0.161.0"
   Looking in indexes: http://localhost:8080/simple/
   ERROR: Could not find a version that satisfies the requirement fastapi==0.161.0 (from versions: 0.162.0)
   ERROR: No matching distribution found for fastapi==0.161.0

Both failures are the index working as intended. A compromised ``fastapi`` release
published on PyPI tonight looks exactly like the second case: it is not in the index, so
nothing installs it.

Now compare an index started **without** ``--disable-fallback``:

.. code-block:: bash

   $ pip install --index-url http://localhost:8081/simple/ requests
   Looking in indexes: http://localhost:8081/simple/
   Collecting requests
     Downloading requests-2.34.2-py3-none-any.whl.metadata (4.8 kB)

pip reports the internal index, and installs ``requests`` from PyPI anyway, through the
redirect. Nothing in the output warns you. Check that flag on any pypiserver you rely
on.

The build backend is a dependency too. Remove ``setuptools-*.whl`` from the index and
the editable install fails:

.. code-block:: bash

   $ pip install --no-deps -e .
   ...
         ERROR: Could not find a version that satisfies the requirement setuptools>=68 (from versions: none)
         ERROR: No matching distribution found for setuptools>=68
         [end of output]
   ...
   × pip subprocess to install build dependencies did not run successfully.

Before the index existed, that unpinned ``setuptools>=68`` was fetched from PyPI on
every CI run, and nobody noticed.

.. warning::

   **Never use** ``--extra-index-url`` **to "add" an internal index next to PyPI.** pip
   does not prefer either index. It collects candidates from **all** of them and picks
   the **highest version**. In February 2021, the security researcher Alex Birsan
   uploaded packages to PyPI and npm using the names of **internal** packages from
   Apple, Microsoft, PayPal and dozens of other companies, with very high version
   numbers. Their build systems, configured with an extra index, installed his public
   packages instead of their own and ran his code inside their networks. The attack
   is now known as **dependency confusion**. Use one index, ``--index-url``, and let
   that index decide what exists.

-----

Docker Builds
--------------

The production image runs ``pip install -r requirements.lock`` in its builder stage
(:ref:`ch04_multistage`). Docker exposes **build arguments** to ``RUN`` instructions as
environment variables, and pip reads ``PIP_INDEX_URL``. So one ``ARG`` in the builder
stage is all it takes:

.. code-block:: dockerfile

   FROM python:3.12.16-trixie AS builder

   # Where pip downloads packages from. Build args are visible to RUN as
   # environment variables, and pip reads PIP_INDEX_URL. Point it at the
   # internal index with:  --build-arg PIP_INDEX_URL=http://localhost:8080/simple/
   ARG PIP_INDEX_URL=https://pypi.org/simple/

   RUN python -m venv /opt/venv

The default keeps ``docker build .`` working for anyone without the index. To build
through it:

.. code-block:: bash

   $ docker build --network host \
       --build-arg PIP_INDEX_URL=http://localhost:8080/simple/ -t bookshelf:mirror .
   ...
   #12 0.353 Looking in indexes: http://localhost:8080/simple/
   #12 0.435   Downloading http://localhost:8080/packages/fastapi-0.162.0-py3-none-any.whl (148 kB)
   #12 0.576   Downloading http://localhost:8080/packages/psycopg_binary-3.3.6-cp312-cp312-manylinux_2_27_aarch64...
   #12 3.866 Successfully installed annotated-doc-0.0.5 annotated-types-0.8.0 ...

``--network host`` lets the build reach ``localhost:8080``. Without it, ``localhost``
inside the build is the build container itself.

The argument is declared in the **builder** stage only. Only the final stage becomes the
image, so the index URL does not appear in the image's history or environment:

.. code-block:: bash

   $ docker history --no-trunc bookshelf:mirror | grep -c PIP_INDEX_URL
   0

.. warning::

   An index that requires a login tempts you to put the password in the URL:
   ``https://ci:s3cret@pypi.internal/simple/``. Do not pass that as a build argument
   that ends up in the **final** stage, where ``docker history`` prints it for anyone
   who pulls the image (:ref:`ch04_multistage`). For credentials, use a BuildKit secret
   mount, which is never stored in any layer:
   ``RUN --mount=type=secret,id=pip_index_url,env=PIP_INDEX_URL pip install ...``,
   built with ``docker build --secret id=pip_index_url,env=PIP_INDEX_URL``.

-----

In the Pipeline
----------------

Both workflows read the index from a **repository variable** (:ref:`ch05_secrets_environments`)
and fall back to PyPI when it is not set. In ``ci.yml``, at the top level:

.. code-block:: yaml

   # Package index for every pip install, including the one in the Docker build.
   # Set the repository variable PIP_INDEX_URL to use an internal index.
   env:
     PIP_INDEX_URL: ${{ vars.PIP_INDEX_URL || 'https://pypi.org/simple/' }}

Every ``pip install`` step in every job inherits the environment variable. The Docker
build does not inherit the runner's environment, so the ``build`` job in ``ci.yml`` and
``build-and-push`` in ``cd.yml`` pass it explicitly:

.. code-block:: yaml

   - uses: docker/build-push-action@v7
     with:
       # ...
       build-args: PIP_INDEX_URL=${{ env.PIP_INDEX_URL }}

``cd.yml`` gets the same ``PIP_INDEX_URL`` line in its ``env:`` block. These are the
only differences between the workflows on :ref:`ch05_full_pipeline` and
:ref:`ch05_docker_in_ci` and the final files in ``support/bookshelf-ch5-solution/``.

**Where the index has to be.** A GitHub-hosted runner is a VM on the internet. It
cannot reach ``localhost:8080`` on your laptop, or a server on a private company
network. In practice there are two setups:

- The index is published on the internet with HTTPS and authentication, and CI logs in
  with a secret, as in the warning above.
- CI runs on **self-hosted runners** inside the company network, next to the index. This
  is common in companies that run an internal index in the first place. The warning
  about self-hosted runners and public repositories in :ref:`ch05_actions_basics`
  applies.

For this course the variable stays unset, so the labs keep using PyPI in CI. In a
company you would also **remove the fallback** (``PIP_INDEX_URL: ${{ vars.PIP_INDEX_URL
}}``, plus a step that fails if it is empty). Otherwise a variable deleted by mistake
silently sends every build back to PyPI.

-----

The Workflow for a New Dependency
----------------------------------

With an internal index, adding a dependency becomes a reviewed change in its own right:

#. A developer adds ``requests`` to ``pyproject.toml`` and re-runs ``pip-compile``. The
   lockfile diff shows ``requests`` **and** its transitive dependencies
   (``charset-normalizer``, ``urllib3``, …).
#. CI, configured with the internal index, fails: ``No matching distribution found for
   requests``. The red build is the trigger for review, not a bug.
#. Someone vets each **new** package in the diff. Who maintains it? How old is it? Does
   the PyPI file match the source repository's release? Is the name a typo of a popular
   package (``reqeusts``)?
#. They run ``populate.sh`` with the new lockfile, so only the reviewed versions enter
   the index, and re-run CI.

Upgrades work the same way: the lockfile diff names exactly which versions change, and
only those are downloaded.

-----

Curated Index or Caching Proxy?
--------------------------------

``populate.sh`` + pypiserver is a **curated** index: nothing enters without an explicit
step. The other common design is a **pull-through caching proxy**: the internal server
forwards requests for missing packages to PyPI and keeps a copy of everything it ever
serves.

.. list-table::
   :header-rows: 1
   :widths: 26 37 37

   * -
     - Curated (pypiserver + populate)
     - Caching proxy (devpi, Nexus, Artifactory, AWS CodeArtifact)
   * - Package deleted from PyPI
     - Protected
     - Protected, once cached
   * - New compromised release
     - Blocked until someone adds it
     - Installed and cached if anything asks for it
   * - Adding a dependency
     - Manual step (the review)
     - Automatic
   * - Typical place
     - Small teams, regulated environments, air-gapped networks
     - Large organisations, combined with scanning and allow-lists

Many organisations end up in between: a caching proxy with policies that quarantine
releases younger than a few days, or that block packages with known vulnerabilities.
The idea is the same either way: **your** server decides what exists, and nothing
installs from the public index directly.

.. admonition:: Observation:

   An internal index controls **which files** are available. It does not prove that a
   file is the one you reviewed: whoever can write to ``packages/`` can replace it.
   Chapter 10 closes that gap with **hash-pinned** lockfiles
   (``pip-compile --generate-hashes``, ``pip install --require-hashes``). pip then refuses
   any file whose SHA-256 differs from the one recorded at review time, whichever index
   served it. Chapter 10 also uses the same pypiserver to publish the team's **own**
   packages.

-----

**Exercises**

#. Populate the index from ``bookshelf-ch5-solution/requirements-dev.lock`` and start
   it. Open ``http://localhost:8080/simple/`` in a browser. How many projects are listed?
   Compare that with the number of ``==`` lines in the lockfile.

#. In a fresh Python 3.12 virtual environment (or the container from the note above),
   install BookShelf entirely from the index with ``PIP_INDEX_URL`` set. Run the tests.
   Confirm that every ``Downloading`` line points at ``localhost:8080``.

#. Try to install ``requests`` and ``fastapi==0.161.0`` from the index and read the
   errors. Then start a second pypiserver on port 8081 **without**
   ``--disable-fallback`` (same ``packages`` directory) and install ``requests``
   from it. Run the install with ``-v`` and find the URL that the package actually came
   from.

#. Set ``index-url`` in your user ``pip.conf``. Then run ``PIP_INDEX_URL=https://pypi.org/simple/
   pip download --no-deps requests``. Which setting wins? Remove the setting afterwards
   with ``pip config --user unset global.index-url``. You will need PyPI again for the
   rest of the course.

#. Build the production image through the index with ``--network host`` and
   ``--build-arg PIP_INDEX_URL=...``. Check the build log for ``Looking in indexes`` and
   confirm with ``docker history --no-trunc`` that the URL is not in the image.

#. Simulate adding a dependency: add ``requests`` to ``dependencies`` in
   ``pyproject.toml``, re-run both ``pip-compile`` commands, and install from the index.
   Which packages are missing? Vet them (check each on pypi.org: maintainers, release
   history, source link), then run ``populate.sh`` with the new lockfile and install
   again. Revert the change when done.

#. Add ``PIP_INDEX_URL`` to the top-level ``env:`` of ``ci.yml`` and ``build-args`` to
   both image builds. Push without setting the repository variable, and verify in the
   logs that CI still uses ``https://pypi.org/simple/``. Then set the variable to
   ``http://localhost:8080/simple/`` and push again. Which step fails in each job, and
   with what error? Why can't the runner reach your index? Delete the variable
   afterwards.
