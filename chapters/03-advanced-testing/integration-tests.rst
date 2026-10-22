.. _ch03_integration_tests:

Integration Testing with TestClient
=====================================

.. admonition:: Crash Course: HTTP Request and Response
   :class: dropdown

   HTTP is a request-response protocol. A client sends a request; a server sends a
   response. Every HTTP interaction has the same structure.

   **Request structure:**

   .. code-block:: text

      POST /books HTTP/1.1
      Host: localhost:8000
      Content-Type: application/json

      {"title": "Clean Code", "author": "Robert Martin", "isbn": "9780132350884", "year": 2008}

   - **Method** (``POST``, ``GET``, ``PUT``, ``DELETE``) — what operation to perform
   - **Path** (``/books``) — which resource
   - **Headers** — metadata (content type, auth tokens, etc.)
   - **Body** — data sent with the request (JSON for API calls, empty for GET)

   **Response structure:**

   .. code-block:: text

      HTTP/1.1 201 Created
      Content-Type: application/json

      {"id": 1, "title": "Clean Code", "author": "Robert Martin", "isbn": "9780132350884", "year": 2008}

   - **Status code** — 2xx success, 4xx client error, 5xx server error
   - **Headers** — metadata about the response
   - **Body** — the response data

   **Common status codes:**

   - ``200 OK`` — request succeeded, body contains result
   - ``201 Created`` — resource was created, body contains the new resource
   - ``204 No Content`` — success, no body (used for DELETE)
   - ``400 Bad Request`` — client sent invalid data (validation error)
   - ``404 Not Found`` — resource does not exist
   - ``409 Conflict`` — duplicate resource (e.g., duplicate ISBN)
   - ``422 Unprocessable Entity`` — FastAPI's validation error (malformed request body)
   - ``500 Internal Server Error`` — server-side bug

   **REST conventions followed by the BookShelf API:**

   .. code-block:: text

      POST   /books              → create a book          → 201
      GET    /books              → list books             → 200
      GET    /books/{id}         → get one book           → 200 or 404
      PUT    /books/{id}         → update a book          → 200 or 404
      DELETE /books/{id}         → delete a book          → 204 or 404
      POST   /books/{id}/reviews → add a review           → 201 or 404
      GET    /books/{id}/reviews → list reviews for book  → 200 or 404

   For a deeper dive, see: `MDN HTTP overview <https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview>`_

-----

What Integration Tests Verify
-------------------------------

Unit tests verify that individual functions produce correct outputs for given inputs. They
say nothing about the HTTP layer: whether routes are registered, whether request parsing
works, whether error responses have the right shape, or whether FastAPI's validation
interacts correctly with the service layer.

Integration tests fill this gap. A FastAPI integration test sends a real HTTP request
through the application stack — route matching, request parsing, the service layer, and
the database — and asserts on the response status code, headers, and body.

The question they answer: does the full request-to-response chain work correctly?

-----

FastAPI's TestClient
---------------------

FastAPI ships with a ``TestClient`` (built on ``httpx``) that runs the application
in-process without starting a real server. Requests and responses are real HTTP, but
no network socket is involved — everything stays inside the same Python process.

Install the dependency:

.. code-block:: bash

   $ pip install httpx

The ``TestClient`` is a drop-in HTTP client with the same interface as ``requests``:

.. code-block:: python

   from fastapi.testclient import TestClient
   from bookshelf.main import app

   client = TestClient(app)

   response = client.get("/books/1")
   print(response.status_code)   # 200 or 404
   print(response.json())        # parsed response body

``TestClient`` supports all HTTP methods (``get``, ``post``, ``put``, ``delete``) and
accepts ``json=``, ``params=``, and ``headers=`` arguments.

-----

Isolating the Test Database
-----------------------------

The application's ``get_connection()`` opens a SQLite file at a fixed path inside the
package directory. Integration tests must not write to this file — tests would pollute
each other and leave state between runs.

The solution: redirect the ``DB_PATH`` to a temporary directory for each test run.
FastAPI lets you override dependencies at test time using ``monkeypatch``:

.. code-block:: python

   # tests/integration/conftest.py
   import pytest
   from fastapi.testclient import TestClient

   from bookshelf.database import init_db
   from bookshelf.main import app


   @pytest.fixture
   def client(tmp_path, monkeypatch):
       db_path = tmp_path / "test.db"
       monkeypatch.setattr("bookshelf.database.DB_PATH", db_path)
       init_db()
       with TestClient(app) as c:
           yield c

How this works:

- ``tmp_path`` is a pytest built-in fixture that provides a unique temporary directory
  per test. Pytest cleans it up after the test completes.
- ``monkeypatch.setattr`` replaces ``bookshelf.database.DB_PATH`` with the temp path.
  When ``get_connection()`` is subsequently called, it opens the temp file.
- ``init_db()`` creates the schema in the new temp database.
- The ``with TestClient(app) as c:`` block starts the application lifespan (which calls
  ``init_db()`` again — harmless, it uses ``CREATE TABLE IF NOT EXISTS``).
- ``monkeypatch`` automatically restores the original ``DB_PATH`` after the test.

Each test that uses the ``client`` fixture gets a fresh, isolated database.

-----

Your First Integration Tests
------------------------------

Create ``tests/integration/test_books_api.py``:

.. code-block:: python

   from fastapi.testclient import TestClient


   def test_create_book_returns_201(client: TestClient) -> None:
       response = client.post("/books/", json={
           "title": "The Pragmatic Programmer",
           "author": "David Thomas",
           "isbn": "9780135957059",
           "year": 1999,
       })
       assert response.status_code == 201
       data = response.json()
       assert data["title"] == "The Pragmatic Programmer"
       assert data["author"] == "David Thomas"
       assert data["isbn"] == "9780135957059"
       assert "id" in data


   def test_get_book_returns_200(client: TestClient) -> None:
       # Create first
       create_response = client.post("/books/", json={
           "title": "Clean Code",
           "author": "Robert Martin",
           "isbn": "9780132350884",
           "year": 2008,
       })
       book_id = create_response.json()["id"]

       # Then fetch
       response = client.get(f"/books/{book_id}")
       assert response.status_code == 200
       assert response.json()["title"] == "Clean Code"


   def test_get_nonexistent_book_returns_404(client: TestClient) -> None:
       response = client.get("/books/99999")
       assert response.status_code == 404
       assert "detail" in response.json()

Run them:

.. code-block:: bash

   $ pytest tests/integration/ -v
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf-ch3
   configfile: pyproject.toml
   collected 3 items

   tests/integration/test_books_api.py::test_create_book_returns_201      PASSED [ 33%]
   tests/integration/test_books_api.py::test_get_book_returns_200         PASSED [ 66%]
   tests/integration/test_books_api.py::test_get_nonexistent_book_returns_404 PASSED [100%]

   ============================== 3 passed in 0.18s ==============================

-----

Testing Error Responses
------------------------

Integration tests are the right place to verify error response shape. The unit tests
confirmed the service logic; the integration tests confirm the HTTP layer translates
errors correctly:

.. code-block:: python

   def test_create_duplicate_isbn_returns_409(client: TestClient) -> None:
       book_data = {
           "title": "Clean Code",
           "author": "Robert Martin",
           "isbn": "9780132350884",
           "year": 2008,
       }
       client.post("/books/", json=book_data)
       response = client.post("/books/", json=book_data)   # duplicate

       assert response.status_code == 409
       assert "ISBN" in response.json()["detail"]


   def test_create_book_invalid_isbn_returns_422(client: TestClient) -> None:
       response = client.post("/books/", json={
           "title": "X",
           "author": "Y",
           "isbn": "not-an-isbn",
           "year": 2020,
       })
       assert response.status_code == 422   # FastAPI validation error


   def test_update_nonexistent_book_returns_404(client: TestClient) -> None:
       response = client.put("/books/99999", json={"title": "New Title"})
       assert response.status_code == 404


   def test_delete_nonexistent_book_returns_404(client: TestClient) -> None:
       response = client.delete("/books/99999")
       assert response.status_code == 404

.. admonition:: Observation:

   FastAPI returns ``422 Unprocessable Entity`` (not ``400 Bad Request``) when Pydantic
   validation fails on the request body. The ``422`` body includes a ``detail`` array
   that describes every field that failed validation — useful for debugging but
   important to assert on in tests. A ``400`` from your own route code versus a ``422``
   from FastAPI's validation layer are different things.

-----

Testing Pagination
-------------------

Pagination is a classic source of off-by-one bugs. Integration tests can verify it end-to-end:

.. code-block:: python

   def test_list_books_pagination(client: TestClient) -> None:
       # Create 5 books
       isbns = ["978013235088{}".format(i) for i in range(5)]
       for i, isbn in enumerate(isbns):
           client.post("/books/", json={
               "title": f"Book {i}",
               "author": "Author",
               "isbn": isbn,
               "year": 2020,
           })

       page_1 = client.get("/books/?offset=0&limit=2").json()
       page_2 = client.get("/books/?offset=2&limit=2").json()
       page_3 = client.get("/books/?offset=4&limit=2").json()

       assert len(page_1) == 2
       assert len(page_2) == 2
       assert len(page_3) == 1   # last page, only 1 item left

       # Pages must not overlap
       page_1_ids = {b["id"] for b in page_1}
       page_2_ids = {b["id"] for b in page_2}
       assert page_1_ids.isdisjoint(page_2_ids)

-----

Testing the Full Data Flow
----------------------------

Some bugs only appear when data flows through multiple operations in sequence. This test
creates a book, adds three reviews, and verifies that fetching the reviews returns the
correct data:

.. code-block:: python

   def test_book_review_full_flow(client: TestClient) -> None:
       # Create book
       book = client.post("/books/", json={
           "title": "The Pragmatic Programmer",
           "author": "David Thomas",
           "isbn": "9780135957059",
           "year": 1999,
       }).json()
       book_id = book["id"]

       # Add reviews
       ratings = [5, 4, 3]
       for rating in ratings:
           response = client.post(f"/books/{book_id}/reviews", json={
               "rating": rating,
               "text": f"Rating {rating} stars.",
               "reviewer": f"reviewer_{rating}",
           })
           assert response.status_code == 201

       # Verify all reviews are stored
       reviews_response = client.get(f"/books/{book_id}/reviews")
       assert reviews_response.status_code == 200
       reviews = reviews_response.json()
       assert len(reviews) == 3

       stored_ratings = sorted(r["rating"] for r in reviews)
       assert stored_ratings == sorted(ratings)

.. code-block:: bash

   $ pytest tests/integration/test_books_api.py -v
   ============================= test session starts ==============================
   platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0
   rootdir: /home/student/bookshelf-ch3
   configfile: pyproject.toml
   collected 8 items

   tests/integration/test_books_api.py::test_create_book_returns_201             PASSED [  12%]
   tests/integration/test_books_api.py::test_get_book_returns_200                PASSED [  25%]
   tests/integration/test_books_api.py::test_get_nonexistent_book_returns_404    PASSED [  37%]
   tests/integration/test_books_api.py::test_create_duplicate_isbn_returns_409   PASSED [  50%]
   tests/integration/test_books_api.py::test_create_book_invalid_isbn_returns_422 PASSED [  62%]
   tests/integration/test_books_api.py::test_update_nonexistent_book_returns_404 PASSED [  75%]
   tests/integration/test_books_api.py::test_list_books_pagination               PASSED [  87%]
   tests/integration/test_books_api.py::test_book_review_full_flow               PASSED [ 100%]

   ============================== 8 passed in 0.31s ==============================

-----

**Exercises**

#. Add the ``tests/integration/conftest.py`` with the ``client`` fixture as shown above.
   Create ``tests/integration/__init__.py`` (empty). Run ``pytest tests/integration/ -v``
   to confirm the fixture is discovered and the first tests pass.

#. Write integration tests for all BookShelf API endpoints. Cover at minimum:

   - ``test_list_books_empty`` — empty database returns an empty list (``[]``)
   - ``test_search_books_by_title`` — create a book, then ``GET /books/search?q=...``
     returns it
   - ``test_delete_book_removes_it`` — create, delete, then ``GET /{id}`` returns 404
   - ``test_add_review_to_nonexistent_book_returns_404`` — ``POST /books/99999/reviews``
   - ``test_list_reviews_for_nonexistent_book_returns_404``
   - ``test_top_books_returns_correct_order`` — create two books with reviews where one
     has a higher average rating; verify ``GET /books/top?n=1`` returns the higher-rated
     book

   Aim for at least 15 total test cases across both ``test_books_api.py`` and
   ``test_reviews_api.py``.

#. Write the full data-flow test as shown: create a book, add three reviews with ratings
   5, 4, and 3, then fetch the book's reviews and verify all three are stored with the
   correct ratings. Assert on ``len(reviews) == 3`` and on the stored rating values.
