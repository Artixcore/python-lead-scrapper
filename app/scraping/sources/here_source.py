"""HERE Discover API source.

Docs: https://developer.here.com/documentation/geocoding-search-api/api-reference-swagger.html

Free tier: ~250,000 transactions/month.

The Discover endpoint requires an ``at=lat,lon`` anchor, so we first resolve
the caller's location through the shared Nominatim-backed geocoder (see
``_geocoder.py``).  HERE responses include structured ``contacts`` arrays
with phone numbers and official websites, which map nicely onto our Lead.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient
from app.scraping.sources._geocoder import geocode_request
from app.utils.text_tools import clean_whitespace
from app.utils.url_tools import normalize_url

log = get_logger(__name__)


_HERE_DISCOVER_URL = "https://discover.search.hereapi.com/v1/discover"


class HereSource(BaseSource):
    """HERE /discover adapter."""

    name = "here"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("HereSource requires a non-empty API key.")
        self._api_key = api_key

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        coords = await geocode_request(request, http)
        if coords is None:
            log.debug("HereSource: could not geocode %r", request.location_string())
            return

        lat, lon = coords
        params = {
            "q": request.keyword,
            "at": f"{lat:.6f},{lon:.6f}",
            "limit": str(min(100, max(20, request.max_leads * 2))),
            "apiKey": self._api_key,
        }
        data = await http.get_json(
            _HERE_DISCOVER_URL,
            params=params,
            headers={"Accept": "application/json"},
        )
        if not isinstance(data, dict):
            log.debug("HERE: unexpected response type.")
            return

        items = data.get("items") or []
        if not isinstance(items, list):
            return

        for item in items:
            lead = self._item_to_lead(item, request)
            if lead is not None:
                yield lead

    # ------------------------------------------------------------------ #

    def _item_to_lead(
        self,
        item: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        if not isinstance(item, dict):
            return None

        name = clean_whitespace(item.get("title"))
        if not name:
            return None

        address = item.get("address") or {}
        addr_label = clean_whitespace(address.get("label"))
        city = clean_whitespace(address.get("city")) or request.city
        state = (
            clean_whitespace(address.get("state"))
            or clean_whitespace(address.get("stateCode"))
            or request.state_or_region
        )
        country = (
            clean_whitespace(address.get("countryName"))
            or clean_whitespace(address.get("countryCode"))
            or request.country
        )

        # contacts: list of { phone: [{value: "..."}], www: [{value: "..."}], email: [...] }
        phone, website, email = None, None, None
        for contact in item.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            phone = phone or _first_contact_value(contact.get("phone"))
            website = website or _first_contact_value(contact.get("www"))
            email = email or _first_contact_value(contact.get("email"))

        # categories: list of {id, name, primary}
        category = None
        for c in item.get("categories") or []:
            if isinstance(c, dict):
                if c.get("primary"):
                    category = clean_whitespace(c.get("name"))
                    break
                if category is None:
                    category = clean_whitespace(c.get("name"))
        category = category or request.business_type

        return Lead(
            company_name=name,
            category=category,
            website=normalize_url(website),
            email=email.strip().lower() if isinstance(email, str) else None,
            phone=phone,
            city=city,
            state_or_region=state,
            country=country,
            address=addr_label,
            source_name=self.name,
            source_url=None,
        )


def _first_contact_value(arr: Any) -> str | None:
    if not isinstance(arr, list):
        return None
    for entry in arr:
        if isinstance(entry, dict):
            v = entry.get("value")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None
