from collections import defaultdict, deque
from time import monotonic


class RateLimiter:
    """Prototype per-process limiter. Caller must not persist the client address."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = monotonic()

    def allow(self, key: str) -> bool:
        now = monotonic()
        hits = self._hits[key]
        if now - self._last_cleanup >= self.window_seconds:
            cutoff = now - self.window_seconds
            for address, address_hits in list(self._hits.items()):
                while address_hits and address_hits[0] <= cutoff:
                    address_hits.popleft()
                if not address_hits:
                    self._hits.pop(address, None)
            self._last_cleanup = now
            hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


responses_limiter = RateLimiter(30)
transcribe_limiter = RateLimiter(10)
