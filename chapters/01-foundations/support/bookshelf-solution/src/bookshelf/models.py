from datetime import date

from pydantic import BaseModel, Field, field_validator


class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str
    year: int

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, v: str) -> str:
        digits = v.replace("-", "").replace(" ", "")
        if len(digits) not in (10, 13):
            raise ValueError("ISBN must be 10 or 13 digits")
        return digits

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int) -> int:
        current_year = date.today().year
        if v > current_year:
            raise ValueError(f"Year cannot be in the future (max: {current_year})")
        return v


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


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5, description="Star rating from 1 to 5")
    text: str
    reviewer: str


class ReviewResponse(BaseModel):
    id: int
    book_id: int
    rating: int
    text: str
    reviewer: str
