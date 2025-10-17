from __future__ import annotations

import threading
import time
from typing import Optional


class RateLimiter:
    """Simple token-bucket rate limiter shared across threads."""

    def __init__(self, rate_per_sec: float, burst: int = 1) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")
        self._rate = rate_per_sec
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> None:
        """Block until a token is available (timeout=None means wait indefinitely)."""
        end_time = None if timeout is None else (time.monotonic() + timeout)
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                if elapsed > 0:
                    self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                    self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_time = (1.0 - self._tokens) / self._rate
            if end_time is not None:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("RateLimiter acquire timed out")
                wait_time = min(wait_time, remaining)
            time.sleep(wait_time)
