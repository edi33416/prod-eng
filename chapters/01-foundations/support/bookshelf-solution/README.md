# BookShelf API — Chapter 1 Solution

Complete implementation of the BookShelf API as built in Chapter 1.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Run

```bash
uvicorn bookshelf.main:app --reload
```

Open http://localhost:8000/docs for the interactive API documentation.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /books/ | Create a book |
| GET | /books/ | List books (paginated) |
| GET | /books/search?q= | Search by title or author |
| GET | /books/{id} | Get a book by ID |
| PUT | /books/{id} | Update a book |
| DELETE | /books/{id} | Delete a book |
| POST | /books/{id}/reviews | Add a review |
| GET | /books/{id}/reviews | List reviews for a book |
| GET | /health | Health check |
