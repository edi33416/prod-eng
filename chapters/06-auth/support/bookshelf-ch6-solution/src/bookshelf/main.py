import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bookshelf.auth.config import get_settings
from bookshelf.database import init_db
from bookshelf.routers import auth, books, reviews


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast if JWT_SECRET_KEY is missing or too short
    init_db()
    yield


app = FastAPI(
    title="BookShelf API",
    description="A production-grade book catalog and review service.",
    version="0.6.0",
    lifespan=lifespan,
)

# Browsers only let pages from these origins call the API from JavaScript.
# Comma-separated, e.g. "https://bookshelf.example.com,http://localhost:3000".
_allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # Tokens travel in the Authorization header, not in cookies.
    allow_credentials=False,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI's default 422 body echoes the rejected value back ("input").
    # For a too-short password that is the password itself, which then
    # ends up in client logs, proxies and error trackers. Drop it.
    errors = [
        {k: v for k, v in error.items() if k != "input"} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.include_router(auth.router)
app.include_router(books.router)
app.include_router(reviews.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
