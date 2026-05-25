from pydantic import BaseModel, Field


# TODO: Add field validators for isbn (10 or 13 digits) and year (not in the future)
class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str
    year: int


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    isbn: str
    year: int


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    year: int | None = None


# TODO: Add Field constraints for rating (ge=1, le=5)
class ReviewCreate(BaseModel):
    rating: int
    text: str
    reviewer: str


class ReviewResponse(BaseModel):
    id: int
    book_id: int
    rating: int
    text: str
    reviewer: str
