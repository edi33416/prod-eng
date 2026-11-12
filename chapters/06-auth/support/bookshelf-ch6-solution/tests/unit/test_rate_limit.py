from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from bookshelf.auth.rate_limit import RateLimiter


def _request(ip: str) -> MagicMock:
    request = MagicMock()
    request.client.host = ip
    return request


def test_allows_up_to_limit() -> None:
    limiter = RateLimiter(times=3, seconds=60)
    for _ in range(3):
        limiter(_request("10.0.0.1"))


def test_rejects_over_limit_with_retry_after() -> None:
    limiter = RateLimiter(times=3, seconds=60)
    for _ in range(3):
        limiter(_request("10.0.0.1"))
    with pytest.raises(HTTPException) as exc_info:
        limiter(_request("10.0.0.1"))
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "60"}


def test_counts_each_ip_separately() -> None:
    limiter = RateLimiter(times=1, seconds=60)
    limiter(_request("10.0.0.1"))
    limiter(_request("10.0.0.2"))


def test_window_slides() -> None:
    limiter = RateLimiter(times=1, seconds=60)
    with patch("bookshelf.auth.rate_limit.time.monotonic", return_value=1000.0):
        limiter(_request("10.0.0.1"))
    with patch("bookshelf.auth.rate_limit.time.monotonic", return_value=1060.5):
        limiter(_request("10.0.0.1"))
