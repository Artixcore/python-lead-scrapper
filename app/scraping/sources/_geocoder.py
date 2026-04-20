"""Shared Nominatim geocoder for sources that need lat/lon.

HERE's Discover endpoint wants ``at=lat,lon`` coordinates, and a few other
future sources will too.  We cache per-process so running a 50-lead job
through two location-keyed sources only costs one Nominatim lookup.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.config import settings
from app.logging_config import get_logger
from app.models.lead_request import LeadRequest
from app.scraping.base import HTTPClient

log = get_logger(__name__)


# Module-level cache: "city, region, country" -> (lat, lon) or None.
# Small enough (hundreds of entries at worst) that we don't bother with LRU.
_CACHE: dict[str, Optional[tuple[float, float]]] = {}
_LOCK = asyncio.Lock()


async def geocode_request(
    request: LeadRequest,
    http: HTTPClient,
) -> Optional[tuple[float, float]]:
    """Return ``(lat, lon)`` for the request's location, or None."""
    key = request.location_string().strip().lower()
    if not key:
        return None

    async with _LOCK:
        if key in _CACHE:
            return _CACHE[key]

    coords = await _geocode(key, http)

    async with _LOCK:
        _CACHE[key] = coords
    return coords


async def _geocode(
    location: str,
    http: HTTPClient,
) -> Optional[tuple[float, float]]:
    base = settings.nominatim_url.rstrip("/")
    params = {
        "q": location,
        "format": "json",
        "limit": "1",
        "addressdetails": "0",
    }
    data = await http.get_json(
        f"{base}/search",
        params=params,
        headers={"User-Agent": settings.nominatim_user_agent},
    )
    if not isinstance(data, list) or not data:
        log.debug("Geocoder: no results for %r", location)
        return None
    try:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
    except (KeyError, ValueError, TypeError):
        log.debug("Geocoder: malformed result for %r: %r", location, data[0])
        return None
    return (lat, lon)


def clear_cache() -> None:
    """Flush the cache.  Intended for tests."""
    _CACHE.clear()
