.. _ch03_testing_pyramid:

The Testing Pyramid
====================

.. note::

   This chapter builds on the BookShelf API from Chapter 2. You will need the working
   project from ``support/bookshelf-ch3/``. Start from there if you want a clean baseline.
   No Docker or external services are needed — all tests run locally.

-----

The Outage That Took Four Hours to Diagnose
--------------------------------------------

A production service starts returning 500 errors. The monitoring alert fires at 3 AM.
The on-call engineer starts investigating. The application logs are clean. The database
is responding normally. The health endpoint returns ``{"status": "ok"}``.

After four hours of digging, the engineer finds the root cause: a change to the book
search endpoint introduced a regression in how pagination interacts with filtering. The
unit tests passed — the business logic was correct in isolation. But nobody had tested
the full HTTP request path. The bug only appeared when the route parameter parsing,
the service function, and the database query all ran together.

There were unit tests. There were zero integration tests.

-----

Three Kinds of Tests
---------------------

Automated tests are not all the same. They differ in scope, speed, and what they verify:

**Unit tests** test a single function or class in isolation. Dependencies are replaced
with test doubles or controlled inputs. Unit tests are fast (milliseconds), cheap to
write, and tell you exactly which unit is broken. The Ch2 test suite consists entirely
of unit tests: ``calculate_average_rating``, ``validate_isbn``, ``create_book`` with a
real but isolated SQLite connection.

**Integration tests** test multiple components working together — typically the full HTTP
request-to-response path through a running application. They exercise the interaction
between the route handler, service layer, and database. Slower than unit tests, but they
catch bugs that only appear when components interact.

**End-to-end (E2E) tests** test the entire system from the outside, including external
services, the reverse proxy, and any dependent infrastructure. They are the slowest,
most expensive to maintain, and the most realistic. A full browser test that creates a
book, adds a review, and verifies the catalog is an E2E test.

-----

The Pyramid Shape
------------------

The testing pyramid describes the recommended distribution of test types:

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────────┐
   │                                                                 │
   │                           /\                                    │
   │                          /  \    End-to-End                     │
   │                         / E2E\   (few, slow, expensive)         │
   │                        /──────\                                 │
   │                       /        \                                │
   │                      /Integration\ (moderate quantity,          │
   │                     /─────────────\  medium speed)              │
   │                    /               \                            │
   │                   /   Unit Tests    \ (many, fast, cheap)       │
   │                  /───────────────────\                          │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘

The pyramid shape has a simple logic:

- **Many unit tests** because they are fast to run and cheap to maintain. Write one for
  every function, every branch, every edge case. Your IDE can run them on every save.

- **Fewer integration tests** because they are slower and require more setup. Write one
  for every significant API endpoint — the happy path and the key error cases.

- **Very few E2E tests** because they are expensive, brittle, and slow. Reserve them for
  critical user journeys: "can a user create an account and complete a purchase?"

The pyramid shape is an investment allocation, not a quality hierarchy. Unit tests are
not "less real" than E2E tests. They catch different bugs, faster and more precisely.

-----

The Anti-Pattern: The Ice Cream Cone
--------------------------------------

The pyramid has an inverse: the ice cream cone. It is what happens when teams skip
unit tests and rely on E2E tests for everything.

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────────┐
   │                                                                 │
   │                  ┌─────────────────────────┐                   │
   │                  │   E2E  (many, slow)      │                   │
   │                  └───────────┬─────────────┘                   │
   │                              │                                  │
   │                         ┌────┴────┐                             │
   │                         │  Integ. │                             │
   │                         └────┬────┘                             │
   │                              │                                  │
   │                           ┌──┴──┐                               │
   │                           │ Unit│  (few)                        │
   │                           └─────┘                               │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘

Teams with this pattern suffer:

- **Slow feedback.** A full E2E run takes minutes or hours. Developers stop running
  the suite locally and wait for CI. They push broken code more often.
- **Flaky tests.** E2E tests depend on timing, external services, and browser state.
  They fail intermittently, eroding trust in the suite. Teams start ignoring failures.
- **Poor diagnosis.** A failing E2E test tells you "something is wrong." A failing unit
  test tells you "the pagination calculation in ``list_books`` is wrong." The E2E failure
  can take hours to trace to root cause.
- **High maintenance.** UI or API changes break dozens of E2E tests simultaneously.
  The cost of keeping them passing discourages adding new tests.

-----

Where Each Test Type Fits in the BookShelf API
------------------------------------------------

The BookShelf API has three distinct layers. Each layer maps naturally to a test type:

**Business logic (unit tests) — what Ch2 covered:**

- ``validate_isbn`` — validates ISBN format
- ``calculate_average_rating`` — computes mean rating
- ``create_book``, ``get_book``, ``search_books`` — data operations through a
  controlled SQLite connection
- Input validation via Pydantic models

These are fast, precise, and run in isolation. They verify that each function does
exactly what it claims.

**API layer (integration tests) — what this chapter adds:**

- Does ``POST /books`` return 201 with the created book body?
- Does ``GET /books/99999`` return 404 with the correct error message?
- Does ``GET /books?offset=2&limit=2`` return the right page?
- Does creating a book, adding reviews, and fetching it via ``GET /books/{id}`` all
  work correctly end-to-end through HTTP?

These tests use FastAPI's ``TestClient`` to exercise the full HTTP path — route handling,
service layer, and a real (in-memory) SQLite database. They are slower than unit tests
but still fast enough to run on every commit.

**Full-stack (E2E) — not covered in this course:**

E2E tests with a reverse proxy, TLS, and a production database belong in a dedicated E2E
suite. They are outside the scope of this course, but they exist for context: after the
CI/CD pipeline in Ch5 deploys the service, a health check and a handful of smoke tests
verify the deployment succeeded.

-----

The Chapter Plan
-----------------

This chapter works through the testing pyramid from bottom to top:

#. **Mocking** — isolating units from external dependencies using ``unittest.mock``
#. **Integration tests** — testing the BookShelf API over HTTP using ``TestClient``
#. **Test isolation** — keeping tests independent with fixture factories
#. **Coverage** — measuring and interpreting test coverage with ``pytest-cov``
#. **Regression pipeline** — a single command that runs all quality checks

By the end, the test suite will cover all API endpoints, all business logic, and all
error paths. The regression pipeline will become the foundation for Ch5's CI/CD workflow.
