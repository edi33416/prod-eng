from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bookshelf.database import init_db
from bookshelf.routers import books, reviews


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # TODO: Call init_db() here so tables are created at startup (not at import time).
    yield


app = FastAPI(
    title="BookShelf API",
    description="A production-grade book catalog and review service.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(books.router)
app.include_router(reviews.router)


# TODO: Add a GET /health endpoint that returns {"status": "ok"}.
