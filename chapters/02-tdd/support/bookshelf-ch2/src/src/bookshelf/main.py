from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bookshelf.database import init_db
from bookshelf.routers import books, reviews


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="BookShelf API",
    description="A production-grade book catalog and review service.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(books.router)
app.include_router(reviews.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
