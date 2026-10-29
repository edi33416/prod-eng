.. _ch04_multistage:

Multi-Stage Builds and Image Security
======================================

What Ships With Your Code
--------------------------

Here is a Dockerfile that looks reasonable and is common in the wild. It is convenient
during development — one image runs the app, the tests, and the linters:

.. code-block:: dockerfile

   # Dockerfile.naive — do not ship this
   FROM python:3.12
   WORKDIR /app
   COPY pyproject.toml requirements.lock ./
   COPY src/ ./src/
   COPY tests/ ./tests/
   RUN pip install --no-cache-dir -e ".[dev]"
   EXPOSE 8000
   CMD ["uvicorn", "bookshelf.main:app", "--host", "0.0.0.0", "--port", "8000"]

Build it and look at what is inside:

.. code-block:: bash

   $ docker build -f Dockerfile.naive -t bookshelf:naive .
   $ docker images bookshelf
   REPOSITORY   TAG      IMAGE ID       CREATED          SIZE
   bookshelf    naive    33d788bdd89d   1 second ago     1.25GB
   bookshelf    v1       552b5d7832a4   54 seconds ago   195MB

   $ docker run --rm --entrypoint sh bookshelf:naive -c \
       'echo "debs: $(dpkg -l | grep -c ^ii)"; for t in gcc make git curl wget pytest ruff; do command -v $t >/dev/null && echo "  has $t"; done; whoami'
   debs: 467
     has gcc
     has make
     has git
     has curl
     has wget
     has pytest
     has ruff
   root

1.25 GB, 467 Debian packages, a C compiler, ``git``, ``curl``, and the whole test
toolchain — all running as root. Each of those matters in production:

- **Attack surface.** Every package is code that can have a CVE. Vulnerability scanners
  (Chapter 10) report on *everything in the image*, used or not. 467 packages means a
  long report and a lot of patching you did not need to do.
- **Post-exploitation toolkit.** If an attacker gets code execution through an
  application bug, ``curl``/``wget`` let them download a payload and ``gcc`` lets them
  compile it — on your server, as root.
- **Pull time.** Every new host, every autoscaling event, every CI runner pulls the
  image. 1.25 GB versus 200 MB is the difference between seconds and minutes when a
  service needs to scale up *now*.

-----

Multi-Stage Builds
-------------------

A multi-stage Dockerfile has several ``FROM`` instructions. Each starts a new stage
with a fresh filesystem. Later stages can ``COPY --from=<stage>`` files out of earlier
ones; **only the last stage becomes the image**. Everything else — compilers, headers,
pip caches — is discarded.

.. code-block:: text

   ┌─────────────────────────────┐          ┌─────────────────────────────┐
   │ builder: python:3.12 (1 GB) │          │ runtime: python:3.12-slim   │
   │                             │          │                             │
   │  gcc, headers, pip          │          │                             │
   │  /opt/venv  ────────────────┼── COPY ─▶│  /opt/venv                  │
   │                             │          │  /app/src                   │
   └─────────────────────────────┘          │  USER appuser               │
          (discarded)                       └─────────────────────────────┘
                                                     (shipped)

Replace the ``Dockerfile`` with:

.. code-block:: dockerfile

   # ---- Stage 1: build ---------------------------------------------------------
   FROM python:3.12.16-trixie AS builder

   RUN python -m venv /opt/venv
   ENV PATH="/opt/venv/bin:$PATH"

   WORKDIR /build
   COPY requirements.lock .
   RUN pip install --no-cache-dir -r requirements.lock

   # ---- Stage 2: runtime -------------------------------------------------------
   FROM python:3.12.16-slim-trixie

   RUN useradd --create-home --uid 10001 appuser

   COPY --from=builder /opt/venv /opt/venv
   ENV PATH="/opt/venv/bin:$PATH" \
       PYTHONPATH=/app/src \
       PYTHONDONTWRITEBYTECODE=1 \
       PYTHONUNBUFFERED=1

   WORKDIR /app
   COPY src/ ./src/

   USER appuser
   EXPOSE 8000
   CMD ["uvicorn", "bookshelf.main:app", "--host", "0.0.0.0", "--port", "8000"]

What changed and why:

- **The builder uses the full image.** It has ``gcc`` and development headers, so any
  dependency without a pre-built wheel for your platform can still compile. None of
  that reaches the runtime stage.
- **Dependencies go into a virtual environment at /opt/venv.** A venv is a single
  self-contained directory, so one ``COPY --from`` moves all of it. It also silences
  pip's "running as root" warning: you are no longer writing into the system Python.
- **Builder and runtime use the same Python version** (``3.12.16``, Debian ``trixie``).
  A venv contains symlinks to the interpreter and compiled extensions built for that
  exact ABI. Copying a 3.12 venv into a 3.13 image breaks in confusing ways.
- **useradd + USER.** The process runs as an unprivileged user with a fixed UID.
- ``PYTHONDONTWRITEBYTECODE`` stops Python from trying to write ``.pyc`` files into the
  root-owned source tree; ``PYTHONUNBUFFERED`` makes log lines appear in
  ``docker logs`` immediately instead of in 4 KB chunks.

Build it:

.. code-block:: bash

   $ docker build --progress=plain -t bookshelf:v2 .
   #5 [builder 1/5] FROM docker.io/library/python:3.12.16-trixie
   #6 [stage-1 1/5] FROM docker.io/library/python:3.12.16-slim-trixie
   #8 [builder 2/5] RUN python -m venv /opt/venv
   #9 [stage-1 2/5] RUN useradd --create-home --uid 10001 appuser
   #9 DONE 0.4s
   #8 DONE 3.3s
   #10 [builder 3/5] WORKDIR /build
   #11 [builder 4/5] COPY requirements.lock .
   #12 [builder 5/5] RUN pip install --no-cache-dir -r requirements.lock
   #12 DONE 8.4s
   #13 [stage-1 3/5] COPY --from=builder /opt/venv /opt/venv
   #13 DONE 0.5s
   #14 [stage-1 4/5] WORKDIR /app
   #15 [stage-1 5/5] COPY src/ ./src/
   ...
   real    0m13.212s

BuildKit runs independent steps of different stages **in parallel** — ``#8`` and
``#9`` overlap. ``stage-1`` is the name Docker gives the unnamed final stage.

-----

The Non-Root Crash
-------------------

Run it:

.. code-block:: bash

   $ docker run --rm -p 8000:8000 bookshelf:v2
   INFO:     Started server process [1]
   INFO:     Waiting for application startup.
   ERROR:    Traceback (most recent call last):
     ...
     File "/app/src/bookshelf/main.py", line 12, in lifespan
       init_db()
     File "/app/src/bookshelf/database.py", line 37, in init_db
       with get_connection() as conn:
            ^^^^^^^^^^^^^^^^
     File "/app/src/bookshelf/database.py", line 8, in get_connection
       conn = sqlite3.connect(DB_PATH)
              ^^^^^^^^^^^^^^^^^^^^^^^^
   sqlite3.OperationalError: unable to open database file

   ERROR:    Application startup failed. Exiting.

This is the image working *correctly*. ``DB_PATH`` points into
``/app/src/bookshelf/``, which is owned by root. ``appuser`` cannot create files there —
and should not be able to. If the application can write to its own code directory, so
can an attacker who finds a bug in it.

As root, the v1 image hid a design problem: the location of the database was hardcoded,
and it was inside the application package. The fix is to make it **configuration**.
Change the top of ``src/bookshelf/database.py``:

.. code-block:: python

   import os
   import sqlite3

   DEFAULT_DATABASE_URL = "sqlite:///bookshelf.db"


   def _sqlite_path(url: str) -> str:
       if not url.startswith("sqlite:///"):
           scheme = url.split(":", 1)[0]
           raise ValueError(
               f"Unsupported DATABASE_URL scheme {scheme!r}: only sqlite:/// is supported"
           )
       return url.removeprefix("sqlite:///")


   DB_PATH = _sqlite_path(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))

The rest of the file is unchanged. Three deliberate choices:

- The variable is a **URL**, ``DATABASE_URL``, the de-facto convention used by Heroku,
  Render, Fly.io, and most libraries. ``sqlite:///bookshelf.db`` is a relative path;
  ``sqlite:////app/data/bookshelf.db`` (four slashes) is absolute. You will add
  ``postgresql://`` support in :ref:`ch04_migrate_postgres`.
- Anything else **fails fast at import time** with a clear message, instead of being
  treated as a weird file name. Misconfiguration should crash on startup, not on the
  first request.
- The error message prints only the scheme, never the full URL. Database URLs contain
  passwords, and error messages end up in logs.

Now give ``appuser`` exactly one writable directory and point the default URL at it.
In the runtime stage, after ``COPY src/``:

.. code-block:: dockerfile

   WORKDIR /app
   COPY src/ ./src/

   # The only directory the app may write to. Code stays root-owned and read-only.
   RUN mkdir /app/data && chown appuser:appuser /app/data
   ENV DATABASE_URL=sqlite:////app/data/bookshelf.db

   USER appuser

Rebuild and run:

.. code-block:: bash

   $ docker build -t bookshelf:v2 .
   $ docker run -d --name bookshelf -p 8000:8000 bookshelf:v2
   4bcfbbbfa8bb577a49fc849430142f4176c69ad1657e027f061c554ad882dc70

   $ docker logs bookshelf
   INFO:     Started server process [1]
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

   $ docker exec bookshelf whoami
   appuser
   $ docker exec bookshelf id
   uid=10001(appuser) gid=10001(appuser) groups=10001(appuser)

   $ docker exec bookshelf ls -la /app /app/data
   /app:
   total 20
   drwxr-xr-x 1 root    root    4096 Oct 28 18:12 .
   drwxr-xr-x 1 root    root    4096 Oct 28 18:12 ..
   drwxr-xr-x 1 appuser appuser 4096 Oct 28 18:12 data
   drwxr-xr-x 3 root    root    4096 May 30 14:34 src

   /app/data:
   total 32
   drwxr-xr-x 1 appuser appuser  4096 Oct 28 18:12 .
   drwxr-xr-x 1 root    root     4096 Oct 28 18:12 ..
   -rw-r--r-- 1 appuser appuser 20480 Oct 28 18:12 bookshelf.db

Code: root-owned, read-only to the process. Data: in one well-known directory, owned by
the process. That directory is also exactly where you would mount a volume to persist
the data — :ref:`ch04_networking_volumes` does that.

Run the test suite on the host to confirm the refactor did not break anything (the
integration fixture still monkeypatches ``DB_PATH``, so no test changes are needed):

.. code-block:: bash

   $ pytest -q
   ...
   73 passed in 0.57s

-----

Comparing the Images
---------------------

.. code-block:: bash

   $ docker images bookshelf
   REPOSITORY   TAG        IMAGE ID       CREATED              SIZE
   bookshelf    v2         ffba3b653bba   4 seconds ago        198MB
   bookshelf    naive      33d788bdd89d   44 seconds ago       1.25GB
   bookshelf    v1         552b5d7832a4   About a minute ago   195MB

   $ for img in bookshelf:naive bookshelf:v1 bookshelf:v2; do
       echo "== $img"
       docker run --rm --entrypoint sh $img -c \
         'echo "debs: $(dpkg -l | grep -c ^ii)"; command -v gcc; whoami'
     done
   == bookshelf:naive
   debs: 467
   /usr/bin/gcc
   root
   == bookshelf:v1
   debs: 87
   root
   == bookshelf:v2
   debs: 87
   appuser

.. list-table::
   :header-rows: 1
   :widths: 22 14 16 16 16

   * - Image
     - Size
     - Debian pkgs
     - Compiler
     - User
   * - ``naive`` (full, dev deps)
     - 1.25 GB
     - 467
     - yes
     - root
   * - ``v1`` (slim, single stage)
     - 195 MB
     - 87
     - no
     - root
   * - ``v2`` (multi-stage)
     - 198 MB
     - 87
     - no
     - appuser

.. admonition:: Observation:

   Be honest about where the savings came from. Going from ``naive`` to ``v1`` — a
   ``slim`` base and no dev dependencies — removed over 1 GB. ``v2`` is the same size as
   ``v1``, because **every BookShelf dependency ships a pre-built wheel**, so ``v1``
   never needed a compiler in the first place.

   Multi-stage earns its keep the day a dependency does *not* have a wheel for your
   platform (a new Python release, an unusual architecture, a package that needs
   ``libpq-dev`` or ``build-essential``). With a single-stage slim image you would have
   to ``apt install`` the toolchain — and ship it. With a builder stage, the toolchain
   stays behind. Multi-stage also gives you a clean place for steps like compiling
   frontend assets or generating code, which you never want in the runtime image.

Use ``docker history`` to see what each layer contributes:

.. code-block:: bash

   $ docker history bookshelf:v2
   IMAGE          CREATED          CREATED BY                                      SIZE
   ffba3b653bba   4 seconds ago    CMD ["uvicorn" "bookshelf.main:app" "--host"…   0B
   <missing>      4 seconds ago    EXPOSE map[8000/tcp:{}]                         0B
   <missing>      4 seconds ago    USER appuser                                    0B
   <missing>      4 seconds ago    ENV DATABASE_URL=sqlite:////app/data/bookshe…   0B
   <missing>      4 seconds ago    RUN /bin/sh -c mkdir /app/data && chown appu…   0B
   <missing>      4 seconds ago    COPY src/ ./src/ # buildkit                     10.6kB
   <missing>      18 seconds ago   WORKDIR /app                                    0B
   <missing>      18 seconds ago   ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/l…   0B
   <missing>      18 seconds ago   COPY /opt/venv /opt/venv # buildkit             53.6MB
   <missing>      30 seconds ago   RUN /bin/sh -c useradd --create-home --uid 1…   8.92kB
   <missing>      16 hours ago     CMD ["python3"]                                 0B
   ...
   <missing>      42 hours ago     # debian.sh --arch 'amd64' out/ 'trixie' '@1…   101MB

Your application is 10.6 kB. Its dependencies are 53.6 MB. The rest is Debian and
Python. Notice also that the ``ENV DATABASE_URL=...`` value is printed in full — which
leads to the next topic.

-----

Image Security Checklist
-------------------------

**Use minimal base images.** ``-slim`` (Debian, glibc) is the safe default for Python.
``-alpine`` is smaller but uses musl libc; many Python wheels are built for glibc, so
on Alpine pip often falls back to compiling from source — slower builds, occasionally
subtle runtime differences. Distroless images (no shell at all) are smaller still, at
the cost of not being able to ``docker exec ... sh`` for debugging.

**Run as a non-root user.** ``USER appuser`` with a fixed numeric UID. Container root
is host root unless user namespaces are configured; a container escape from a root
process is a host compromise.

**Never put secrets in the image.** Not in ``COPY``, not in ``ENV``, not in ``ARG``.
Every layer and every piece of metadata is readable by anyone who can pull the image:

.. code-block:: bash

   $ docker history --no-trunc bookshelf:v2 | grep DATABASE_URL
   $ docker image inspect bookshelf:v2 --format '{{json .Config.Env}}'

Deleting a file in a later layer does not help — the earlier layer still contains it.
Secrets are supplied at **runtime**, through environment variables or mounted files
(next pages).

**Pin base image versions.** ``python:3.12-slim`` is a moving tag: it was Debian 12 last
year and is Debian 13 today. ``python:3.12.16-slim-trixie`` pins the Python patch
version and the OS release, so an unrelated upstream change does not alter your image
between two builds of the same commit. For full reproducibility, pin the digest as well:

.. code-block:: dockerfile

   FROM python:3.12.16-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

Pinning does not mean freezing: update the pin deliberately (Dependabot and Renovate
can open PRs for this), rebuild, and let CI test it.

**Scan images for known vulnerabilities.** Tools such as Trivy, Grype, and Docker Scout
compare every package in an image against CVE databases. Chapter 10 integrates
scanning into the pipeline; for now, notice that a smaller image is a shorter report.

-----

**Exercises**

#. Build ``Dockerfile.naive`` and inspect it with the ``dpkg``/``command -v`` loop above.
   Record its size, package count, and user.

#. Convert your ``Dockerfile`` to the multi-stage build shown on this page *without* the
   ``/app/data`` lines. Build ``bookshelf:v2`` and run it. Confirm you get the
   ``unable to open database file`` error and explain it in one sentence.

#. Apply the ``DATABASE_URL`` change to ``database.py``, add the ``/app/data``
   directory to the Dockerfile, and rebuild. Then verify:

   .. code-block:: bash

      $ docker run -d --name bookshelf -p 8000:8000 bookshelf:v2
      $ docker exec bookshelf whoami          # must print appuser
      $ docker exec bookshelf touch /app/src/evil.py   # must fail
      $ curl -s localhost:8000/health

   Run ``pytest`` on the host to make sure all tests still pass.

#. Compare the three images with ``docker images bookshelf``. Then run
   ``docker run --rm -e DATABASE_URL=mysql://x bookshelf:v2`` and read the error. Does
   the message reveal anything sensitive?

#. Run ``docker image inspect bookshelf:v2 --format '{{json .Config.Env}}'``. Imagine a
   colleague added ``ENV API_KEY=...`` to the Dockerfile. Who could read it?

#. **(Optional)** Make the builder stage necessary: add ``psycopg[c]`` (the C-extension
   build of the PostgreSQL driver, which needs ``libpq-dev`` and ``gcc``) to the
   lockfile. Try installing it in a single-stage ``python:3.12-slim`` image and observe
   the failure. Then install it in the builder stage and add only the runtime library
   (``apt-get install -y --no-install-recommends libpq5``) to the runtime stage. Compare
   image sizes.
