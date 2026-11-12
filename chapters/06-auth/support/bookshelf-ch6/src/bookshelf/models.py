from datetime import date

from pydantic import BaseModel, Field, SecretStr, field_validator


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
    # TODO(ch6): anyone can claim to be anyone. Take the reviewer from the
    # access token instead (see implementing-jwt.rst).
    reviewer: str


class ReviewResponse(BaseModel):
    id: int
    book_id: int
    rating: int
    text: str
    reviewer: str


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    # Lowercase letters, digits, "_" and "-". The ":" used by "github:<login>"
    # accounts is deliberately not allowed, so the two can never collide.
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_-]+$")
    # SecretStr prints as '**********' in reprs, logs and tracebacks.
    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: SecretStr) -> SecretStr:
        # Length is what makes a password strong (NIST SP 800-63B); the upper
        # bound stops someone from making us hash a 10 MB "password".
        if not 12 <= len(v.get_secret_value()) <= 128:
            raise ValueError("Password must be between 12 and 128 characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: SecretStr


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
