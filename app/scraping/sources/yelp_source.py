"""Yelp Fusion API source.

Docs: https://docs.developer.yelp.com/reference/v3_business_search

Free tier: 500 calls/day.  One call returns up to 50 businesses, so a single
search covers almost any job this bot would realistically run.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient
from app.utils.text_tools import clean_whitespace
from app.utils.url_tools import normalize_url

log = get_logger(__name__)


_YELP_ENDPOINT = "https://api.yelp.com/v3/businesses/search"


# Light mapping from our canonical business_type to Yelp category slugs.
# Yelp's "categories" parameter is a comma-separated list of slugs.
# https://docs.developer.yelp.com/docs/resources-categories
_YELP_CATEGORY_MAP: dict[str, str] = {
    "dentist": "dentists",
    "doctors": "physicians",
    "clinic": "medcenters",
    "hospital": "hospitals",
    "pharmacy": "pharmacy",
    "veterinary": "vet",
    "restaurant": "restaurants",
    "cafe": "cafes",
    "bar": "bars",
    "bakery": "bakeries",
    "hotel": "hotels",
    "fitness_centre": "gyms",
    "hairdresser": "hair",
    "plumber": "plumbing",
    "electrician": "electricians",
    "lawyer": "lawyers",
    "accountant": "accountants",
    "real_estate_agency": "realestateagents",
    "marketing_agency": "marketing",
    "advertising_agency": "advertising",
    "it_company": "itservices",
}


class YelpSource(BaseSource):
    """Yelp Fusion adapter."""

    name = "yelp"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("YelpSource requires a non-empty API key.")
        self._api_key = api_key

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        location = request.location_string()
        if not location:
            # Yelp requires either location or (lat, lon). We only have the
            # former without extra geocoding.
            return

        params: dict[str, str | int] = {
            "location": location,
            "limit": min(50, max(10, request.max_leads * 2)),
            "term": request.keyword,
        }
        cat = _YELP_CATEGORY_MAP.get(request.business_type or "")
        if cat:
            params["categories"] = cat

        data = await http.get_json(
            _YELP_ENDPOINT,
            params=params,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )
        if not isinstance(data, dict):
            log.debug("Yelp: unexpected response type.")
            return

        businesses = data.get("businesses") or []
        if not isinstance(businesses, list):
            return

        for b in businesses:
            lead = self._business_to_lead(b, request)
            if lead is not None:
                yield lead

    # ------------------------------------------------------------------ #

    def _business_to_lead(
        self,
        b: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        if not isinstance(b, dict):
            return None

        name = clean_whitespace(b.get("name"))
        if not name:
            return None

        # Category label: first category's "title"
        category = None
        cats = b.get("categories") or []
        if isinstance(cats, list) and cats:
            first = cats[0]
            if isinstance(first, dict):
                category = clean_whitespace(first.get("title"))
        category = category or request.business_type

        loc = b.get("location") or {}
        addr1 = loc.get("address1") or ""
        addr_disp = loc.get("display_address") or []
        if isinstance(addr_disp, list) and addr_disp:
            address = clean_whitespace(", ".join(str(x) for x in addr_disp if x))
        else:
            address = clean_whitespace(addr1) or None

        city = clean_whitespace(loc.get("city")) or request.city
        state = clean_whitespace(loc.get("state")) or request.state_or_region
        country = clean_whitespace(loc.get("country")) or request.country

        phone = clean_whitespace(
            b.get("display_phone") or b.get("phone")
        )

        # Yelp's `url` is the yelp page, not the company's website.  We store
        # it as source_url; website stays None here -- the enrichment step
        # will try to follow the Yelp page later if we choose to.
        yelp_url = normalize_url(b.get("url"))

        return Lead(
            company_name=name,
            category=category,
            website=None,
            email=None,
            phone=phone,
            city=city,
            state_or_region=state,
            country=country,
            address=address,
            source_name=self.name,
            source_url=yelp_url,
        )
