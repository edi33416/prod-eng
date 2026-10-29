.. _ch04_docker_basics:

Docker Fundamentals
====================

Before containerizing the BookShelf API, get comfortable with the handful of commands
you will use every day. Everything on this page is disposable — nothing touches the
project yet.

-----

Installing Docker
------------------

On Ubuntu, the distribution package is the quickest route:

.. code-block:: bash

   $ sudo apt update
   $ sudo apt install -y docker.io docker-compose-v2
   $ sudo usermod -aG docker "$USER"     # run docker without sudo
   $ newgrp docker                       # or log out and back in

On macOS and Windows, install `Docker Desktop <https://docs.docker.com/desktop/>`_
(on Windows, enable the WSL2 backend). Docker Desktop includes the Compose plugin.

.. warning::

   Membership in the ``docker`` group is equivalent to root on that machine: anyone who
   can talk to the Docker daemon can start a container that mounts ``/`` from the host.
   Fine on your own workstation; think twice before granting it on a shared server.

Verify the installation:

.. code-block:: bash

   $ docker run hello-world
   Unable to find image 'hello-world:latest' locally
   latest: Pulling from library/hello-world
   58dee6a49ef1: Pull complete
   Digest: sha256:c567b231f65614688711a75f31518a064258a51d442117a3e771a3a8fdba78ef
   Status: Downloaded newer image for hello-world:latest

   Hello from Docker!
   This message shows that your installation appears to be working correctly.
   ...

Read the first four lines carefully — they show the whole image lifecycle. Docker looked
for ``hello-world:latest`` locally, did not find it, pulled it from the registry layer by
layer, verified its digest, and then created and ran a container from it.

-----

Images, Containers, Layers
---------------------------

An image is a stack of read-only **layers**. Each layer is a filesystem diff: "add these
files, change those". Layers are identified by content hash, so two images built on
``python:3.12-slim`` share its layers on disk and in the registry.

When you run a container, Docker adds one thin **writable layer** on top. Everything the
process writes — log files, a SQLite database, ``apt install`` results — goes into that
layer. Remove the container and the writable layer is gone.

.. note::

   A container is an **instance** of an image. One image can have many containers
   running at the same time, each with its own writable layer, process tree, and
   network address, all sharing the same read-only image layers underneath. It is the
   same relationship as between a binary on disk and its processes: run
   ``/usr/bin/python3`` three times and you get three independent processes from one
   executable file. ``docker run bookshelf:v1`` three times gives you three independent
   containers from one image.

.. code-block:: text

   ┌─────────────────────────────┐
   │ writable container layer    │  ← deleted with the container
   ├─────────────────────────────┤
   │ COPY src/ ./src/            │  ┐
   │ RUN pip install …           │  │ read-only image layers,
   │ python:3.12-slim layers     │  │ shared between containers
   │ debian:trixie-slim layers   │  ┘
   └─────────────────────────────┘

This one fact explains most beginner surprises with Docker: "I installed a package in
the container and it disappeared" and "my database was empty after I recreated the
container" are the same thing.

-----

Containers Are Ephemeral
-------------------------

Treat a container as disposable: **anything you do inside it is lost when the
container is removed.** That covers installed packages, edited config files, and data
written by the application. This is by design. It is what lets you replace a container
with a fresh one from the same image at any time.

.. code-block:: bash

   $ docker run --name eph ubuntu:24.04 bash -c 'echo "important" > /notes.txt'
   $ docker rm eph
   eph
   $ docker run --rm ubuntu:24.04 cat /notes.txt
   cat: /notes.txt: No such file or directory

Data that must outlive the container goes in a **volume**: storage that lives outside
the container's writable layer and is mounted into it at a path of your choice with
``-v NAME:PATH``:

.. code-block:: bash

   $ docker run --rm -v notes:/data ubuntu:24.04 bash -c 'echo "important" > /data/notes.txt'
   $ docker run --rm -v notes:/data ubuntu:24.04 cat /data/notes.txt
   important
   $ docker volume rm notes
   notes

The first container is gone, but the file in ``/data`` survived and a brand-new
container sees it. Everything outside ``/data`` is still discarded. Volumes in a
multi-container setup are covered in :ref:`ch04_networking_volumes`.

-----

Essential Commands
-------------------

Interactive containers
^^^^^^^^^^^^^^^^^^^^^^^

The general form of ``docker run`` is:

.. code-block:: text

   docker run [OPTIONS] IMAGE[:TAG] [COMMAND] [ARG...]

- ``IMAGE[:TAG]`` selects the image, e.g. ``ubuntu:24.04``. Omit the tag and Docker
  assumes ``:latest``.
- ``COMMAND [ARG...]`` is the process to start inside the container. That program is
  not supplied by your host: it must exist **in the image's filesystem**. ``bash`` below
  is ``/bin/bash`` from the Ubuntu image, not the shell on your machine.

Every image also records a **default command**, used when you give none:

.. code-block:: bash

   $ docker image inspect ubuntu:24.04 --format '{{json .Config.Cmd}}'
   ["/bin/bash"]
   $ docker image inspect python:3.12-slim --format '{{json .Config.Cmd}}'
   ["python3"]

That process becomes PID 1 of the container, and **the container lives exactly as long
as that process**. When it exits, the container stops. Asking for a program the image
does not contain fails immediately, e.g. ``docker run ubuntu:24.04 python3`` reports
``executable file not found in $PATH``.

``-i`` keeps stdin open, ``-t`` allocates a terminal. Together they give you an
interactive shell:

.. code-block:: bash

   $ docker run -it ubuntu:24.04 bash
   root@3c1e2a9b7f40:/# cat /etc/os-release | head -2
   PRETTY_NAME="Ubuntu 24.04.5 LTS"
   NAME="Ubuntu"
   root@3c1e2a9b7f40:/# which python3 || echo "no python3"
   no python3
   root@3c1e2a9b7f40:/# exit

The Ubuntu base image does not even ship Python. Base images are deliberately minimal;
you add exactly what you need.

Listing containers and images
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   $ docker ps                 # running containers only
   CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES

   $ docker ps -a              # include stopped containers
   CONTAINER ID   IMAGE          COMMAND   CREATED          STATUS                     PORTS   NAMES
   3c1e2a9b7f40   ubuntu:24.04   "bash"    48 seconds ago   Exited (0) 5 seconds ago           eager_hopper
   73ef99a53b6d   hello-world    "/hello"  3 minutes ago    Exited (0) 3 minutes ago           funny_murdock

Exited containers stay around until you remove them — including their writable layer.
Docker generated a random name (``eager_hopper``) because we did not pass ``--name``.

.. code-block:: bash

   $ docker images
   REPOSITORY    TAG       IMAGE ID       CREATED        SIZE
   ubuntu        24.04     1f1aeedbd16d   3 days ago     101MB
   hello-world   latest    eb84fdc6f2a3   7 months ago   5.2kB

Pulling images
^^^^^^^^^^^^^^^

``docker run`` pulls implicitly, but pulling explicitly is useful to pre-fetch or to
update a tag:

.. code-block:: bash

   $ docker pull python:3.12-slim
   3.12-slim: Pulling from library/python
   6fc242d221a6: Pull complete
   3eb771151506: Pull complete
   f574edac59d9: Pull complete
   acca7542dfc7: Pull complete
   Digest: sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
   Status: Downloaded newer image for python:3.12-slim
   docker.io/library/python:3.12-slim

Each ``Pull complete`` line is one layer. Pull ``python:3.12`` (the full image) next and
compare sizes with ``docker images python`` — you will come back to this difference in
:ref:`ch04_multistage`.

Running one-off commands
^^^^^^^^^^^^^^^^^^^^^^^^^

Anything after the image name replaces the image's default command:

.. code-block:: bash

   $ docker run python:3.12-slim python -c "print('Hello from Docker')"
   Hello from Docker

Add ``--rm`` to remove the container automatically when it exits. For throwaway commands,
always use it — otherwise ``docker ps -a`` fills up with dead containers.

Background containers, logs, stop, remove
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``-d`` (detached) runs the container in the background; ``-p host:container`` publishes a
port:

.. code-block:: bash

   $ docker run -d --name web -p 8001:8000 python:3.12-slim python -m http.server 8000
   b6c2aa1e3a0a659aff1a1b7e0e3273be16fdb8e7529974d9bf20c9888c9c623c

   $ curl -s -o /dev/null -w "%{http_code}\n" localhost:8001
   200

   $ docker logs web
   172.17.0.1 - - [28/Oct/2026 18:18:03] "GET / HTTP/1.1" 200 -

   $ time docker stop web
   web
   real    0m10.255s

   $ docker rm web
   web

``docker logs`` shows whatever the process wrote to stdout and stderr. That is the
container convention: **log to stdout, let the platform collect it**. You will build on
this in Chapter 8.

.. admonition:: Observation:

   Why did ``docker stop`` take ten seconds? It sends ``SIGTERM`` to PID 1 in the
   container and waits up to 10 s before sending ``SIGKILL``. A process running as PID 1
   gets no default signal handlers from the kernel, and ``http.server`` installs none of
   its own, so it ignores ``SIGTERM`` and is killed after the timeout. Uvicorn *does*
   handle ``SIGTERM`` and shuts down gracefully — provided it really is PID 1, which is
   why the Dockerfile in the next section uses the exec form of ``CMD``.

Getting a shell in a running container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When logs are not enough, ``docker exec`` starts an **additional** process inside a
running container. It sees the same filesystem, network, and environment as the main
process. With ``-it`` and a shell, you are effectively logged into the container:

.. code-block:: bash

   $ docker run -d --name web -p 8001:8000 python:3.12-slim python -m http.server 8000
   $ docker exec -it web bash
   root@3899a360146e:/# cat /proc/1/cmdline | tr '\0' ' '; echo
   python -m http.server 8000
   root@3899a360146e:/# env | grep PYTHON_VERSION
   PYTHON_VERSION=3.12.16
   root@3899a360146e:/# exit

   $ docker exec web whoami          # one-off command, no shell needed
   root

``exit`` ends only your shell. The container keeps running because its PID 1 is still
``http.server``. Things to know when debugging this way:

- **Minimal images lack the usual tools.** ``python:3.12-slim`` has no ``ps``,
  ``curl``, or ``ping`` (``docker exec web ps`` fails with
  ``executable file not found in $PATH``). Use what is there (``/proc``, ``python -c``),
  or reach for ``sh`` if an image has no ``bash`` (Alpine).
- **exec runs as the image's user.** Add ``-u 0`` to get root in an image that runs as
  a non-root user, for example to ``apt-get install`` a debugging tool.
- **Changes are temporary.** Anything you install or edit lives in the container's
  writable layer and disappears with the container. Fix the Dockerfile, not the
  running container.
- **It only works on running containers.** If the container has crashed, read
  ``docker logs`` instead, or start a fresh one with a shell as the command
  (``docker run -it --rm IMAGE bash``) to look around.

Housekeeping
^^^^^^^^^^^^^

.. code-block:: bash

   $ docker container prune    # remove all stopped containers
   $ docker image prune        # remove dangling (untagged) images
   $ docker system df          # disk usage by images, containers, volumes, build cache

Images and build cache grow quickly. ``docker system df`` is the first thing to check
when a CI runner or laptop runs out of disk.

-----

Command Cheat Sheet
--------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Command
     - Purpose
   * - ``docker run [-it] [-d] [--rm] [-p H:C] IMAGE [CMD]``
     - Create and start a container
   * - ``docker ps`` / ``docker ps -a``
     - List running / all containers
   * - ``docker images``
     - List local images
   * - ``docker pull IMAGE[:TAG]``
     - Download an image
   * - ``docker logs [-f] CONTAINER``
     - Show (follow) container output
   * - ``docker exec -it CONTAINER sh``
     - Run a command inside a running container
   * - ``docker stop CONTAINER`` / ``docker rm CONTAINER``
     - Stop (SIGTERM, then SIGKILL) / remove
   * - ``docker rmi IMAGE``
     - Remove an image

-----

**Exercises**

#. Run an interactive Ubuntu container and install Python inside it:

   .. code-block:: bash

      $ docker run -it --name py-test ubuntu:24.04 bash
      root@...:/# apt-get update && apt-get install -y python3
      root@...:/# python3 --version
      root@...:/# exit

   Run ``docker ps`` and ``docker ps -a``. In which list does ``py-test`` appear, and
   what is its status?

#. Start a *new* container from the same image: ``docker run -it --rm ubuntu:24.04 bash``
   and run ``python3 --version``. Is Python installed? Explain the result in terms of
   image layers and the container's writable layer.

#. Restart the stopped ``py-test`` container with ``docker start -ai py-test`` and check
   for Python again. Then remove it with ``docker rm py-test``.

#. Run a one-off command in the official Python image and observe the output:

   .. code-block:: bash

      $ docker run --rm python:3.12-slim python -c "print('Hello from Docker')"
      $ docker run --rm python:3.12-slim python -c "import sys; print(sys.version)"

   Compare the version with ``python3 --version`` on your host.

#. Reproduce the slow ``docker stop`` from the Observation above. Then run the same
   container with ``--init`` (which inserts a tiny init process as PID 1 that forwards
   signals) and time ``docker stop`` again. What changed?
