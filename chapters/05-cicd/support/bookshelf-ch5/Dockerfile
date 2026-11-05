# ---- Stage 1: build ---------------------------------------------------------
FROM python:3.12.16-trixie AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# ---- Stage 2: runtime -------------------------------------------------------
FROM python:3.12.16-slim-trixie

RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY src/ ./src/

# The only directory the app may write to. Code stays root-owned and read-only.
RUN mkdir /app/data && chown appuser:appuser /app/data
ENV DATABASE_URL=sqlite:////app/data/bookshelf.db

USER appuser
EXPOSE 8000
CMD ["uvicorn", "bookshelf.main:app", "--host", "0.0.0.0", "--port", "8000"]
