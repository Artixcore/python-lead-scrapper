"""Base classes for source adapters and a shared async HTTP client."""

from __future__ import annotations

import abc
import asyncio
from typing import AsyncIterator

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.utils.rate_limiter import PerDomainRateLimiter
from app.utils.retries import retry_async

log = get_logger(__name__)


class HTTPClient:
    """Thin async wrapper around ``httpx.AsyncClient`` with polite defaults.

    Usage::

        async with HTTPClient() as client:
            html = await client.get_text(url)
    """

    def __init__(
        self,
        *,
        timeout: float | None = None,
        user_agent: str | None = None,
        rate_limiter: PerDomainRateLimiter | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else settings.http_timeout
        self._user_agent = user_agent or settings.user_agent
        self._rate_limiter = rate_limiter or PerDomainRateLimiter(
            delay=settings.request_delay_seconds,
            max_concurrent=settings.max_concurrent_requests,
        )
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HTTPClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": "en-US,en;q=0.8",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #

    @property
    def rate_limiter(self) -> PerDomainRateLimiter:
        return self._rate_limiter

    async def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Low-level GET with rate-limiting + retries."""
        if self._client is None:
            raise RuntimeError("HTTPClient must be used as an async context manager")

        async def _do() -> httpx.Response:
            await self._rate_limiter.acquire(url)
            try:
                resp = await self._client.get(url, params=params, headers=headers)  # type: ignore[union-attr]
                resp.raise_for_status()
                return resp
            finally:
                self._rate_limiter.release()

        return await retry_async(_do, attempts=3)

    async def get_text(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> str | None:
        """GET and return response.text, or None on any HTTP/network failure."""
        try:
            resp = await self.get(url, params=params, headers=headers)
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            log.debug("HTTP failure for %s: %s", url, e)
            return None
        except Exception as e:  # pragma: no cover
            log.debug("Unexpected HTTP error for %s: %s", url, e)
            return None
        ctype = resp.headers.get("content-type", "")
        if "text" not in ctype and "html" not in ctype and "json" not in ctype:
            return None
        try:
            return resp.text
        except Exception:
            return None

    async def get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict | list | None:
        try:
            resp = await self.get(url, params=params, headers=headers)
            return resp.json()
        except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as e:
            log.debug("JSON GET failed for %s: %s", url, e)
            return None


# --------------------------------------------------------------------------- #
# Source adapter interface
# --------------------------------------------------------------------------- #


class BaseSource(abc.ABC):
    """Interface every lead source must implement."""

    #: Human-readable identifier, e.g. "openstreetmap".
    name: str = "base"

    @abc.abstractmethod
    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        """Yield :class:`Lead` candidates for the request.

        Implementations should be defensive: never raise, always yield what
        they can and log the rest.
        """
        raise NotImplementedError  # pragma: no cover
        # The body must be a generator; we satisfy that via yield inside a
        # subclass. The abstract method can't actually yield.


async def collect_from_source(
    source: BaseSource,
    request: LeadRequest,
    http: HTTPClient,
    limit: int,
) -> list[Lead]:
    """Consume a source's ``search`` generator up to ``limit`` leads.

    Catches exceptions so that one bad source cannot crash the whole job.
    """
    leads: list[Lead] = []
    try:
        agen = source.search(request, http)
        async for lead in agen:
            leads.append(lead)
            if len(leads) >= limit:
                break
    except Exception as e:  # pragma: no cover - defensive
        log.exception("Source '%s' failed: %s", source.name, e)
    return leads
