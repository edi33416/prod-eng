from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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

# TODO(ch6): CORS middleware with origins from CORS_ALLOWED_ORIGINS
# (security-best-practices.rst).

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(reviews.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
