"""Nominatim free-text POI search.

This complements :class:`OSMSource` (which uses Overpass tags) by running a
plain keyword search through Nominatim.  It's useful when the caller's
keyword doesn't map cleanly to our OSM tag table, e.g. "vegan bakery" or
"escape room".

No API key required.  Honors Nominatim's usage policy via a custom
User-Agent that includes the configured contact email.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.config import settings
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient
from app.utils.text_tools import clean_whitespace
from app.utils.url_tools import normalize_url

log = get_logger(__name__)


class NominatimPOISource(BaseSource):
    """Free-text POI search against Nominatim."""

    name = "nominatim_poi"

    def __init__(self) -> None:
        self._base = settings.nominatim_url.rstrip("/")

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        q = self._build_query(request)
        if not q:
            return

        params = {
            "q": q,
            "format": "jsonv2",
            "addressdetails": "1",
            "extratags": "1",
            "namedetails": "1",
            "limit": str(min(50, max(10, request.max_leads * 2))),
        }
        data = await http.get_json(
            f"{self._base}/search",
            params=params,
            headers={"User-Agent": settings.nominatim_user_agent},
        )
        if not isinstance(data, list):
            log.warning("NominatimPOISource: unexpected payload type.")
            return

        seen: set[str] = set()
        for el in data:
            lead = self._element_to_lead(el, request)
            if lead is None:
                continue
            key = (lead.company_name or "").lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            yield lead

    # ------------------------------------------------------------------ #

    def _build_query(self, request: LeadRequest) -> str:
        parts: list[str] = []
        if request.keyword:
            parts.append(request.keyword)
        loc = request.location_string()
        if loc:
            parts.append(loc)
        return ", ".join(parts).strip()

    def _element_to_lead(
        self,
        el: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        if not isinstance(el, dict):
            return None

        # Prefer the "namedetails.name" then the top-level "name", then the
        # leading part of display_name.
        namedetails = el.get("namedetails") or {}
        name = (
            clean_whitespace(namedetails.get("name"))
            or clean_whitespace(el.get("name"))
        )
        if not name:
            display = clean_whitespace(el.get("display_name"))
            if display:
                name = display.split(",", 1)[0].strip() or None
        if not name:
            return None

        extratags = el.get("extratags") or {}
        address = el.get("address") or {}

        website = normalize_url(
            extratags.get("website")
            or extratags.get("contact:website")
            or extratags.get("url")
        )
        email = extratags.get("email") or extratags.get("contact:email")
        phone = (
            extratags.get("phone")
            or extratags.get("contact:phone")
            or extratags.get("contact:mobile")
        )

        city = clean_whitespace(
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or request.city
        )
        state = clean_whitespace(address.get("state") or request.state_or_region)
        country = clean_whitespace(address.get("country") or request.country)

        # Build a readable street address from address parts.
        addr_parts: list[str] = []
        for k in (
            "house_number",
            "road",
            "pedestrian",
            "suburb",
            "city",
            "town",
            "village",
            "postcode",
            "country",
        ):
            v = address.get(k)
            if v and v not in addr_parts:
                addr_parts.append(str(v))
        readable = clean_whitespace(", ".join(addr_parts)) if addr_parts else None

        category = _category_from_element(el) or request.business_type

        osm_type = el.get("osm_type")
        osm_id = el.get("osm_id")
        source_url = (
            f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
            if osm_type and osm_id
            else None
        )

        return Lead(
            company_name=name,
            category=category,
            website=website,
            email=email.strip().lower() if isinstance(email, str) else None,
            phone=phone.strip() if isinstance(phone, str) else None,
            city=city,
            state_or_region=state,
            country=country,
            address=readable,
            source_name=self.name,
            source_url=source_url,
        )


def _category_from_element(el: dict[str, Any]) -> str | None:
    # Nominatim jsonv2 returns "category" + "type", e.g. "amenity"/"cafe".
    cat = el.get("category")
    typ = el.get("type")
    if cat and typ:
        return f"{cat}:{typ}"
    if typ:
        return str(typ)
    return None
