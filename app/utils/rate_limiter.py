"""Per-domain async rate limiter + global concurrency limiter."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from app.utils.url_tools import get_domain


class PerDomainRateLimiter:
    """Ensures at least ``delay`` seconds between requests to each domain.

    Also caps global concurrency via an asyncio semaphore.
    """

    def __init__(self, delay: float = 1.0, max_concurrent: int = 5) -> None:
        self._delay = max(0.0, float(delay))
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_hit: dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrent)))

    async def acquire(self, url_or_domain: str) -> None:
        """Block until it's safe to hit the given URL/domain."""
        domain = get_domain(url_or_domain) or url_or_domain or "_default"
        await self._semaphore.acquire()
        lock = self._locks[domain]
        await lock.acquire()
        try:
            now = time.monotonic()
            last = self._last_hit.get(domain, 0.0)
            wait = self._delay - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[domain] = time.monotonic()
        finally:
            lock.release()

    def release(self) -> None:
        """Release the global concurrency semaphore."""
        self._semaphore.release()

    # Context manager interface
    async def __aenter__(self) -> "PerDomainRateLimiter":  # pragma: no cover
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        return None


class RateLimitedSession:
    """Helper context manager to acquire+release in one call."""

    def __init__(self, limiter: PerDomainRateLimiter, url: str) -> None:
        self._limiter = limiter
        self._url = url

    async def __aenter__(self) -> None:
        await self._limiter.acquire(self._url)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._limiter.release()
