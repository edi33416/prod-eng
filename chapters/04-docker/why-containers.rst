.. _ch04_why_containers:

Why Containers?
================

.. note::

   This chapter starts from the BookShelf API at the end of Chapter 3. A clean copy is
   provided in ``support/bookshelf-ch4/``. The finished state of the chapter (Dockerfile,
   Compose files, PostgreSQL support) is in ``support/bookshelf-ch4-solution/``.

   You need Docker Engine 24+ with the Compose plugin (``docker compose``, not the legacy
   ``docker-compose``), or Docker Desktop on macOS / Windows (WSL2). Budget 8 GB of RAM:
   by the end of the chapter you will run three containers at once.

-----

The Deploy That Only Worked on One Laptop
------------------------------------------

A team ships a reporting service. Every test passes in CI. The deploy to the production
VM succeeds. Within minutes, every PDF export returns a 500 error.

The root cause takes a day to find. The developer's laptop had Python 3.12 and a recent
``libjpeg``; the production VM had Python 3.10 (the distribution default) and a
``libjpeg`` three major versions older. A dependency compiled a C extension against the
local library at install time. Nothing in ``pyproject.toml`` or the lockfile mentioned
``libjpeg`` — it was an *implicit* dependency, inherited from whatever machine ran
``pip install``.

The lockfile from :ref:`ch01_deps` pins every *Python* package. It cannot pin:

- the Python interpreter itself
- system libraries (``libssl``, ``libpq``, ``libjpeg``, glibc)
- OS-level configuration (locale, timezone, CA certificates)
- the database server version the code was tested against

"It works on my machine" is almost always a statement about one of these.

-----

What Containers Solve
----------------------

A **container image** packages the application together with *everything* it needs to
run: the interpreter, system libraries, Python packages, and the application code. The
image is built once and the identical bytes run on a laptop, in CI, and in production.

.. code-block:: text

   ┌──────────────────────────────────────┐
   │  bookshelf:v2 (container image)      │
   │                                      │
   │  /app/src/bookshelf/  ← your code    │
   │  /opt/venv/           ← FastAPI, …   │
   │  /usr/local/bin/python3.12           │
   │  /usr/lib/…/libssl.so.3, libc.so.6   │
   │  Debian 13 userland                  │
   └──────────────────────────────────────┘

Three properties make this valuable in production:

- **Reproducible** — the image is immutable. Rebuilding from the same Dockerfile and
  lockfile gives the same result; running the same image tag gives the same behaviour.
- **Portable** — any host with a container runtime can run it. The host needs a Linux
  kernel and Docker; it does not need Python, PostgreSQL, or any library.
- **Disposable** — containers start in under a second and leave nothing behind when
  removed. Upgrading means "start the new image, stop the old one", not "run apt on a
  live server and hope".

-----

Containers vs Virtual Machines
-------------------------------

Both isolate workloads, but at different levels:

.. code-block:: text

          Virtual machines                         Containers

   ┌────────┐ ┌────────┐ ┌────────┐     ┌────────┐ ┌────────┐ ┌────────┐
   │  App A │ │  App B │ │  App C │     │  App A │ │  App B │ │  App C │
   │  libs  │ │  libs  │ │  libs  │     │  libs  │ │  libs  │ │  libs  │
   │ Kernel │ │ Kernel │ │ Kernel │     └────────┘ └────────┘ └────────┘
   └────────┘ └────────┘ └────────┘     ┌──────────────────────────────┐
   ┌──────────────────────────────┐     │   Container runtime (Docker) │
   │   Hypervisor (KVM, Xen, …)   │     ├──────────────────────────────┤
   ├──────────────────────────────┤     │   Host kernel (shared)       │
   │   Host kernel                │     ├──────────────────────────────┤
   ├──────────────────────────────┤     │   Hardware                   │
   │   Hardware                   │     └──────────────────────────────┘
   └──────────────────────────────┘

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * -
     - Virtual machine
     - Container
   * - Kernel
     - Own kernel per VM
     - Shares the host kernel
   * - Startup time
     - Tens of seconds (boots an OS)
     - Milliseconds (starts a process)
   * - Size
     - Gigabytes (full OS disk image)
     - Megabytes (userland + app only)
   * - Isolation
     - Strong — hardware-enforced boundary
     - Weaker — a kernel bug can be an escape
   * - Typical use
     - Multi-tenant hosting, different OSes
     - Packaging and shipping applications

The two are complementary. In practice, most production containers run *inside* VMs:
the cloud provider gives you a VM, and you run containers on it.

.. admonition:: Observation:

   On macOS and Windows, Docker Desktop runs a small Linux VM and your containers run
   inside it. That is why containers on a Mac are still Linux containers — they need a
   Linux kernel. It is also why bind-mounted files can feel slower on macOS: every file
   access crosses the VM boundary.

.. admonition:: Crash Course: Linux Namespaces and cgroups
   :class: dropdown

   A container is not a lightweight VM. It is an **ordinary Linux process** that the
   kernel has been told to lie to. Two kernel features do the work:

   **Namespaces** control what a process can *see*. Each namespace type gives the
   process its own private view of one global resource:

   - **PID** — the process sees its own process tree; its first process is PID 1
   - **NET** — its own network interfaces, IP addresses, routing table, ports
   - **MNT** — its own filesystem tree (the image's root filesystem, not the host's)
   - **UTS** — its own hostname
   - **IPC**, **USER**, **CGROUP** — shared memory, user ID mapping, cgroup view

   **cgroups** (control groups) control what a process can *use*: memory, CPU time,
   I/O bandwidth, number of processes.

   You can see both from inside a container:

   .. code-block:: bash

      $ docker run --rm alpine:3.20 sh -c 'ps; hostname'
      PID   USER     TIME  COMMAND
          1 root      0:00 sh -c ps; hostname
          7 root      0:00 ps
      e62f9a1d7ca0

   Only two processes are visible, and the shell is PID 1 — the PID namespace hides
   everything else on the host. The hostname is the container ID (UTS namespace).

   Resource limits are cgroup settings, exposed as files:

   .. code-block:: bash

      $ docker run --rm --memory 64m --cpus 0.5 alpine:3.20 \
          sh -c 'cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max'
      67108864
      50000 100000

   64 MiB of memory, and 50 ms of CPU time per 100 ms period (half a core). Exceed the
   memory limit and the kernel's OOM killer terminates the process:

   .. code-block:: bash

      $ docker run --rm --memory 32m python:3.12-slim \
          python -c "x = bytearray(100 * 1024 * 1024)"
      $ echo $?
      137

   Exit code 137 = 128 + 9 (``SIGKILL``). You will see this exit code again when a
   production container is killed for exceeding its memory limit.

   On a Linux host, ``ps aux`` on the host *does* show the container's processes — with
   different PIDs. The isolation is a view, not a separate machine.

   For a deeper dive, see: `namespaces(7) <https://man7.org/linux/man-pages/man7/namespaces.7.html>`_
   and `cgroups(7) <https://man7.org/linux/man-pages/man7/cgroups.7.html>`_

-----

The Container Ecosystem
------------------------

Four terms come up constantly. Keep them distinct:

**Image**
   A read-only template: a stack of filesystem layers plus metadata (default command,
   environment variables, exposed ports). Identified by a name and tag, e.g.
   ``python:3.12-slim`` or ``bookshelf:v2``. Built from a ``Dockerfile``.

**Container**
   A running (or stopped) instance of an image. It adds a thin writable layer on top of
   the image's read-only layers. You can start many containers from one image.

**Registry**
   A server that stores and distributes images. ``docker pull python:3.12-slim`` fetches
   from Docker Hub by default. Companies run private registries — you will set up Harbor
   in Chapter 10.

**Runtime / engine**
   The software that builds images and runs containers. Docker Engine (``dockerd``) is
   the most common; Podman and containerd are alternatives that use the same image
   format (the OCI standard), so images built with Docker run anywhere.

The analogy that helps most: an image is to a container what a class is to an object,
or what an executable file is to a running process.

-----

**Exercises**

#. Verify Docker is installed and the daemon is reachable:

   .. code-block:: bash

      $ docker version --format 'client {{.Client.Version}} / server {{.Server.Version}}'
      $ docker compose version

   If the second command fails but ``docker-compose version`` works, you have the
   legacy v1 tool. Install the Compose v2 plugin — this course uses ``docker compose``.

#. Open the Crash Course block above and run the ``ps; hostname`` command yourself.
   Then run it again. Is the hostname the same? Why not?

#. Run the out-of-memory example and confirm the exit code is ``137``. Now raise the
   limit to ``--memory 256m`` and run it again. What is the exit code now?

#. In two or three sentences, explain to a colleague why a lockfile alone did not
   prevent the ``libjpeg`` incident described at the top of this page, and what a
   container image adds.
