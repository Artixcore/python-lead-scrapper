"""Very thin wrapper around the SQLite page cache."""

from __future__ import annotations

from app.db.sqlite import SQLiteDB
from app.logging_config import get_logger

log = get_logger(__name__)


class CacheService:
    """Async page cache backed by SQLite.

    Used by the website enricher to avoid re-fetching the same homepage multiple
    times across jobs.
    """

    def __init__(self, db: SQLiteDB) -> None:
        self._db = db

    async def get_page(self, url: str) -> str | None:
        try:
            return await self._db.cache_get(url)
        except Exception as e:  # pragma: no cover
            log.debug("Cache get failed for %s: %s", url, e)
            return None

    async def set_page(self, url: str, html: str) -> None:
        if not url or not html:
            return
        try:
            await self._db.cache_set(url, html)
        except Exception as e:  # pragma: no cover
            log.debug("Cache set failed for %s: %s", url, e)
