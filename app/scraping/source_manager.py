"""Orchestrates multiple source adapters."""

from __future__ import annotations

import asyncio

from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient, collect_from_source

log = get_logger(__name__)


class SourceManager:
    """Runs multiple :class:`BaseSource` adapters and merges their output."""

    def __init__(self, sources: list[BaseSource] | None = None) -> None:
        self._sources: list[BaseSource] = sources or []

    # ---- public API ---- #

    def register(self, source: BaseSource) -> None:
        """Register an additional source adapter."""
        self._sources.append(source)

    @property
    def sources(self) -> list[BaseSource]:
        return list(self._sources)

    async def collect(
        self,
        request: LeadRequest,
        http: HTTPClient,
        per_source_limit: int | None = None,
    ) -> list[Lead]:
        """Call every registered source concurrently and return merged leads.

        Sources that raise or time out are logged and skipped.
        """
        if not self._sources:
            log.warning("No sources registered.")
            return []

        limit = per_source_limit or max(10, request.max_leads * 3)

        tasks = [
            asyncio.create_task(
                collect_from_source(src, request, http, limit=limit),
                name=f"src:{src.name}",
            )
            for src in self._sources
        ]

        results: list[Lead] = []
        for src, task in zip(self._sources, tasks):
            try:
                leads = await task
            except Exception as e:  # pragma: no cover - defensive
                log.exception("Source %r failed: %s", src.name, e)
                leads = []
            log.info("Source %r returned %d raw leads.", src.name, len(leads))
            results.extend(leads)
        return results
