"""Placeholder directory source adapter.

This adapter is intentionally conservative: it does NOT scrape any third-party
business directory by default (many directories prohibit automated scraping in
their Terms of Service).  It exists as an extension point so you can plug in
a compliant, licensed directory later (e.g. a government registry or an
open-data business dataset).

When called, it simply yields nothing and logs a hint.  To enable a real
directory, subclass :class:`DirectorySource` and override ``search``.
"""

from __future__ import annotations

from typing import AsyncIterator

from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient

log = get_logger(__name__)


class DirectorySource(BaseSource):
    """No-op directory adapter meant for extension."""

    name = "directory"

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        log.debug(
            "DirectorySource: no-op (plug in a compliant directory adapter to enable). "
            "Request: %s",
            request.pretty(),
        )
        # This is an async generator, so we need an (unreachable) yield.
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        return
