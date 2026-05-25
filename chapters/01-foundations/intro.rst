.. _ch01_intro:

Why Production Engineering?
============================

.. note::

   This chapter requires Python 3.11+ and Git. No Docker or cloud services are needed yet —
   all exercises run locally. Estimated time: 3–4 hours across all sections.

-----

The 3 AM Incident
-----------------

It is 3:17 AM. Your phone rings.

"The site is down." A coworker's message lands in the team chat, followed immediately by a
stream of user complaints on social media. You open your laptop and stare at a cascade of
500 errors. No alerts fired. No dashboard changed color. You found out because a user tweeted.

You SSH into the server — after spending five minutes hunting for the IP address buried in a
Slack message from six months ago. You run ``ps aux | grep python`` and see that the API
process has crashed. You restart it with a bash one-liner you half-remember. The service
comes back up.

But *why* did it crash? You ``grep`` through a ``nohup.out`` file looking for the error
message. It is buried in 80,000 lines of unstructured ``print()`` output from three years of
development. Eventually you find it: a ``KeyError`` on a dictionary, introduced by a new
deployment three days ago. The crash had been silently corrupting roughly 2% of requests
ever since — you just had no way to know.

Four hours. That is how long it took to diagnose a one-line bug.

What Went Wrong
^^^^^^^^^^^^^^^

This incident is not unusual — it is the default outcome when a service lacks the
infrastructure that production systems require. In this case:

- **No automated tests.** The bug was introduced during development but no test caught it.
- **No structured logging.** Diagnosing the failure took an hour of ``grep`` archaeology.
- **No monitoring or alerting.** The team found out from a tweet, not a paging system.
- **No containerization.** Deployment was a manual ``git pull`` and process restart.
- **No CI/CD.** Code went directly from a laptop to production with no automated gate.

Each of these is a solved problem. This course teaches you to solve all of them — for a real
service, from scratch, using the same tools used in production at most software companies.

-----

What This Course Teaches
-------------------------

Production engineering is the discipline of making software *reliably operable* — not just
functional. A feature that works on your laptop but crashes in production is not done. An API
that handles 10 requests per second but falls over at 100 is not production-ready.

This course takes a single web service — the **BookShelf API**, a book catalog and review
system — and progressively hardens it into a production-grade service. By the final chapter,
it will have:

- A full automated test suite with unit tests, mocks, and integration tests
- A containerized deployment with Docker and Docker Compose
- A CI/CD pipeline that lints, tests, builds, and deploys on every push
- A reverse proxy with automatic TLS certificate management
- Structured logging, Prometheus metrics, and Grafana dashboards
- Alerting rules and an on-call incident management workflow
- A private container registry and internal package repository
- An AI-powered recommendation endpoint and an MCP server for agent integration

Each chapter adds one layer. By the end, every box in the checklist below is checked.

The Production Readiness Checklist
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 5 60 15
   :header-rows: 1

   * - Status
     - Requirement
     - Chapter
   * - ☐
     - Automated tests: unit + integration + coverage gate
     - Ch 2–3
   * - ☐
     - Containerized with Docker and Docker Compose
     - Ch 4
   * - ☐
     - CI/CD pipeline: lint → test → build → deploy
     - Ch 5
   * - ☐
     - Reverse proxy with automatic TLS (HTTPS)
     - Ch 6
   * - ☐
     - Structured logging and Prometheus metrics
     - Ch 7
   * - ☐
     - Alerting rules and incident response workflow
     - Ch 8
   * - ☐
     - Private container and package registries
     - Ch 9
   * - ☐
     - AI-powered features via LLM integration
     - Ch 10
   * - ☐
     - AI agent integration via MCP server
     - Ch 11

-----

The BookShelf API
-----------------

The running project for this course is the **BookShelf API**: a RESTful service for managing
a catalog of books and user reviews. It is simple enough to understand fully in one chapter
and complex enough to benefit from every production technique in the chapters that follow.

**What it does:**

- Manage books: create, read, update, delete (CRUD) with title, author, ISBN, and year
- Accept user reviews with star ratings (1–5) and review text
- Search books by title or author
- Expose a health check endpoint (used for monitoring in Ch 7)

**Why this project:**

Every production technique in this course applies naturally to the BookShelf API. Tests
validate business logic (ISBN format, rating ranges). Containers package the app with its
database. Monitoring tracks request latency and error rates. AI endpoints enhance search.

**Technology choices:**

- **FastAPI** — Python web framework with type hints, auto-generated docs, and excellent testability
- **SQLite** — simple, file-based database requiring no server (upgraded to PostgreSQL in Ch 4)
- **Python 3.11+** — required for the modern type hint syntax used throughout

-----

Prerequisites
-------------

This course assumes solid competency in several areas. The techniques covered build on these
foundations — if the prerequisites are shaky, the production engineering concepts will be
harder to absorb. The course does not teach these from scratch; targeted refreshers appear
as collapsible **Crash Course** blocks where they are most relevant.

**Python proficiency**
   You are comfortable writing Python: functions, classes, modules, exceptions, and
   comprehensions. You know how to use ``pip``, virtual environments, and install packages.
   You can read a stack trace and find the line that caused it.

**Linux command line**
   You work comfortably in a terminal: navigating the filesystem, managing files and
   directories, installing packages, reading and writing files with standard tools
   (``cat``, ``grep``, ``sed``, ``awk``), and running background processes.

**Operating systems fundamentals**
   You understand processes and threads: what they are, how they are scheduled, and how
   they communicate. You know what file descriptors are and how the OS manages them. You
   are familiar with signals (``SIGTERM``, ``SIGKILL``) and what happens when a process exits.

**Networking basics**
   You understand TCP/IP at a conceptual level: IP addresses, ports, and the client–server
   model. You know the HTTP request/response cycle — methods, headers, status codes, and
   bodies. You have a working understanding of DNS: what a hostname is and how it resolves
   to an IP address.

**Debugging skills**
   You can debug a running program: you know how to add print statements, read error
   messages, and narrow down a failure to a specific function or line. You have used a
   debugger (``pdb`` or an IDE debugger) at least once, even if it is not your default.

.. note::

   If any of these feel uncertain, that is fine — look for the **Crash Course** blocks
   throughout the chapter that provide quick refreshers on the most relevant concepts.
   For deeper gaps, the course materials include pointers to external resources.

-----

This Chapter
------------

This chapter establishes the foundation. You will:

#. Create a well-structured Python project using the ``src`` layout
#. Configure dependency management with virtual environments and locked requirements
#. Set up automated code quality tools: Ruff (linting + formatting) and mypy (type checking)
#. Install pre-commit hooks so quality gates run automatically before every commit
#. Establish a team Git workflow with branch naming and commit message conventions
#. Build and run the complete BookShelf API with all CRUD, review, and search endpoints

The code you write here is the foundation every subsequent chapter builds on. Take the time
to set it up correctly.
