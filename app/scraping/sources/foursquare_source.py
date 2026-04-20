"""Foursquare Places API v3 source.

Docs: https://location.foursquare.com/developer/reference/place-search

Uses the ``/v3/places/search`` endpoint.  Auth is a raw API key (no
``Bearer`` prefix).  We request extended ``fields`` so we get phone/website
in the primary response rather than having to follow up per-place.
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


_FSQ_ENDPOINT = "https://api.foursquare.com/v3/places/search"

# Comma-separated list of fields we want Foursquare to include in each result.
_FSQ_FIELDS = (
    "fsq_id,name,categories,location,tel,website,email,social_media,"
    "description,link"
)


class FoursquareSource(BaseSource):
    """Foursquare Places v3 adapter."""

    name = "foursquare"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("FoursquareSource requires a non-empty API key.")
        self._api_key = api_key

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        near = request.location_string()
        if not near:
            return

        params = {
            "query": request.keyword,
            "near": near,
            "limit": min(50, max(10, request.max_leads * 2)),
            "fields": _FSQ_FIELDS,
        }
        data = await http.get_json(
            _FSQ_ENDPOINT,
            params=params,
            headers={
                "Authorization": self._api_key,
                "Accept": "application/json",
            },
        )
        if not isinstance(data, dict):
            log.debug("Foursquare: unexpected response type.")
            return

        results = data.get("results") or []
        if not isinstance(results, list):
            return

        for place in results:
            lead = self._place_to_lead(place, request)
            if lead is not None:
                yield lead

    # ------------------------------------------------------------------ #

    def _place_to_lead(
        self,
        place: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        if not isinstance(place, dict):
            return None

        name = clean_whitespace(place.get("name"))
        if not name:
            return None

        # Category label: first entry's `name`.
        category = None
        cats = place.get("categories") or []
        if isinstance(cats, list) and cats:
            first = cats[0]
            if isinstance(first, dict):
                category = clean_whitespace(first.get("name"))
        category = category or request.business_type

        loc = place.get("location") or {}
        address = (
            clean_whitespace(loc.get("formatted_address"))
            or clean_whitespace(loc.get("address"))
        )
        city = (
            clean_whitespace(loc.get("locality"))
            or clean_whitespace(loc.get("dma"))
            or request.city
        )
        state = (
            clean_whitespace(loc.get("region"))
            or request.state_or_region
        )
        country = clean_whitespace(loc.get("country")) or request.country

        website = normalize_url(place.get("website"))
        phone = clean_whitespace(place.get("tel"))
        email = place.get("email")

        # social_media: { "facebook_id": "...", "instagram": "...", "twitter": "..." }
        social = place.get("social_media") or {}
        facebook = _social_url("facebook", social.get("facebook_id"))
        instagram = _social_url("instagram", social.get("instagram"))
        twitter = _social_url("twitter", social.get("twitter"))

        fsq_id = place.get("fsq_id")
        source_url = f"https://foursquare.com/v/{fsq_id}" if fsq_id else None

        return Lead(
            company_name=name,
            category=category,
            website=website,
            email=email.strip().lower() if isinstance(email, str) else None,
            phone=phone,
            city=city,
            state_or_region=state,
            country=country,
            address=address,
            facebook_url=facebook,
            instagram_url=instagram,
            twitter_url=twitter,
            description=clean_whitespace(place.get("description")),
            source_name=self.name,
            source_url=source_url,
        )


def _social_url(platform: str, handle: Any) -> str | None:
    if not isinstance(handle, str) or not handle.strip():
        return None
    h = handle.strip().lstrip("@")
    if platform == "facebook":
        return f"https://www.facebook.com/{h}"
    if platform == "instagram":
        return f"https://www.instagram.com/{h}"
    if platform == "twitter":
        return f"https://twitter.com/{h}"
    return None
