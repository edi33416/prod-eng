import httpx

_OPENLIBRARY_URL = "https://openlibrary.org/api/books"


def validate_isbn_remote(isbn: str) -> bool:
    """Returns True if the ISBN exists in Open Library."""
    response = httpx.get(
        _OPENLIBRARY_URL,
        params={"bibkeys": f"ISBN:{isbn}", "format": "json"},
        timeout=5.0,
    )
    response.raise_for_status()
    return bool(response.json())
