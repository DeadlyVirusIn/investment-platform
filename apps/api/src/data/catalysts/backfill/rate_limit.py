"""Simple per-process rate limiter (thread-safe).

Token-bucket with 1-minute window. Blocks caller up to `max_wait_secs`.
Never crashes — if waited too long, caller can choose to skip.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class RateLimiter:
    max_per_minute: int
    max_wait_secs: float = 60.0

    def __post_init__(self) -> None:
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> bool:
        """Block until we're allowed to proceed. Returns True if accepted,
        False if waited beyond max_wait_secs."""
        deadline = time.monotonic() + self.max_wait_secs
        while True:
            now = time.monotonic()
            with self._lock:
                cutoff = now - 60.0
                while self._events and self._events[0] < cutoff:
                    self._events.popleft()
                if len(self._events) < self.max_per_minute:
                    self._events.append(now)
                    return True
                oldest = self._events[0]
                sleep_for = max(0.0, (oldest + 60.0) - now)
            if now + sleep_for > deadline:
                return False
            time.sleep(min(sleep_for, 1.0))
