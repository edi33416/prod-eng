.. _ch02_why_tdd:

Why Test-Driven Development?
=============================

.. note::

   This chapter builds on the BookShelf API from Chapter 1. You will need the working
   project from ``support/bookshelf-ch2/``. Start from there if you skipped Chapter 1.
   No Docker or external services are needed — all tests run locally.

-----

The "Small Fix" Incident
-------------------------

It is a Friday afternoon. A developer pushes a one-line change to fix a rounding error in
the payment processing logic. The code review looks fine. CI passes. The change is merged.

Two hours later, the support queue starts filling up. Customers cannot complete purchases.
The payment system is rejecting all transactions over $1,000. The "small fix" introduced an
off-by-one error in the amount validation that only manifests for large values.

Revenue loss: significant. Emergency rollback: required. Post-mortem: painful.

There were no automated tests for the payment validation logic. The developer tested manually
with a $10 charge. Nobody tested with $1,000. Nobody thought to.

What Automated Tests Give You
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The immediate instinct is "we should have tested that." But tests are not just about catching
that specific bug. They change how you work:

- **Confidence to refactor.** When you have a test suite that verifies correct behavior, you
  can restructure code without fear. Without tests, every change is risky. With tests, the
  suite tells you immediately if you broke something.

- **Living documentation.** A test named ``test_payment_rejected_when_amount_exceeds_limit``
  is clearer than any comment. It shows exactly what the code is supposed to do — and it
  verifies it on every run.

- **Regression prevention.** Once a bug is fixed, write a test that reproduces it. That bug
  can never silently reappear — the test will catch it.

- **Faster feedback than manual testing.** Running 200 unit tests takes 0.3 seconds. Running
  the same checks manually takes 20 minutes. Tests win.

-----

The TDD Cycle
--------------

Test-Driven Development is a discipline, not just a testing strategy. The cycle has three
steps:

.. code-block:: text

   ┌─────────────────────────────────────────────────────┐
   │                                                     │
   │    RED  → Write a failing test                      │
   │          Describe the behavior you want.            │
   │          Run it. It must fail (behavior not yet     │
   │          implemented).                              │
   │                                                     │
   │  GREEN  → Write the minimum code to pass            │
   │          No gold-plating. Just enough to make the   │
   │          test go green. Ugly code is fine here.     │
   │                                                     │
   │ REFACTOR → Clean up                                 │
   │          Improve structure, naming, and clarity.    │
   │          Tests remain green throughout.             │
   │                                                     │
   └─────────────────────────────────────────────────────┘

The cycle is short — typically 2–10 minutes per loop. You accumulate a test suite that
describes exactly what the system does, built incrementally as features are developed.

The Red Step Matters
^^^^^^^^^^^^^^^^^^^^^

Why must the test fail first? Because a test that passes before you write the code is not
testing anything. It might be testing the wrong thing, or always passing regardless of the
implementation. Seeing the test fail — and for the *right reason* — confirms you have written
a meaningful test.

.. admonition:: Observation:

   The TDD constraint "write tests first" is often resisted by developers who feel it slows
   them down. In practice, TDD replaces a different, slower loop: write code → manually test
   in the browser/terminal → discover it is wrong → fix → repeat. The test suite makes the
   feedback loop mechanical and milliseconds fast.

-----

When TDD Works Best
--------------------

TDD shines for:

- **Business logic and validation rules** — ISBN format, rating ranges, date constraints
- **Data transformations** — average rating calculation, search result ranking
- **Edge cases** — empty inputs, boundary values, duplicate entries
- **Bug fixes** — write a test that reproduces the bug, then fix it

TDD is harder for:

- **User interfaces** — visual output is difficult to assert on mechanically
- **Complex external integrations** — database schemas, third-party APIs (addressed in Ch 3
  with mocks and integration tests)
- **Exploratory code** — prototyping an unfamiliar API

The BookShelf API has a rich layer of business logic — validation, search, rating
aggregation — that is a natural fit for TDD. This is what you will focus on throughout
this chapter.

-----

What This Chapter Builds
-------------------------

By the end of this chapter, the BookShelf API will have:

- A complete unit test suite covering all business logic
- A ``services.py`` module that separates business logic from HTTP and database concerns
- A structured ``tests/`` directory with named conventions and shared fixtures
- Pytest configured with markers so slow tests can be skipped during development

The architectural change introduced here — separating business logic into a testable
``services.py`` layer — is the foundation that Chapter 3's integration tests, and every
subsequent chapter, will build on.
