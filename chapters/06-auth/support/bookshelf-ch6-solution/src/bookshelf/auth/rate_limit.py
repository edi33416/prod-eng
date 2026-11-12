import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding-window limit of `times` requests per `seconds`, per client IP.

    State lives in this process's memory. With several workers or replicas,
    each one counts separately; move the counters to Redis or enforce the
    limit at the reverse proxy (Chapter 7).
    """

    def __init__(self, times: int, seconds: float) -> None:
        self.times = times
        self.seconds = seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.seconds:
                hits.popleft()
            if len(hits) >= self.times:
                retry_after = math.ceil(hits[0] + self.seconds - now)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_rate_limit = RateLimiter(times=5, seconds=60)
