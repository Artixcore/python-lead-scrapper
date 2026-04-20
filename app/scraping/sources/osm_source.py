"""OpenStreetMap source adapter.

Uses Nominatim to resolve the user's location into an area and Overpass to
query for amenities / offices / shops matching the requested business type.
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


# Map canonical business_type (from normalizers.BUSINESS_TYPE_MAP) to a list of
# (osm_key, osm_value) tag pairs to search in Overpass.  Using multiple tags
# lets a single request cover related OSM categorizations.
_OSM_TAG_MAP: dict[str, list[tuple[str, str]]] = {
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "doctors": [("amenity", "doctors"), ("healthcare", "doctor")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic")],
    "hospital": [("amenity", "hospital"), ("healthcare", "hospital")],
    "pharmacy": [("amenity", "pharmacy"), ("healthcare", "pharmacy")],
    "veterinary": [("amenity", "veterinary")],
    "real_estate_agency": [("office", "estate_agent"), ("shop", "estate_agent")],
    "it_company": [("office", "it"), ("office", "company")],
    "marketing_agency": [("office", "marketing"), ("office", "advertising_agency")],
    "advertising_agency": [("office", "advertising_agency"), ("office", "advertising")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "bakery": [("shop", "bakery")],
    "hotel": [("tourism", "hotel")],
    "fitness_centre": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "hairdresser": [("shop", "hairdresser"), ("shop", "beauty")],
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
}


class OSMSource(BaseSource):
    """OpenStreetMap (Nominatim + Overpass) source adapter."""

    name = "openstreetmap"

    def __init__(self) -> None:
        self._nominatim = settings.nominatim_url.rstrip("/")
        self._overpass = settings.overpass_url

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        area_id = await self._resolve_area(request, http)
        if area_id is None:
            log.info("OSMSource: could not resolve location for %r", request.location_string())
            return

        tags = self._tags_for_request(request)
        if not tags:
            log.info(
                "OSMSource: no OSM tag mapping for business_type=%r; "
                "falling back to keyword name search.",
                request.business_type,
            )

        query = self._build_overpass_query(
            area_id=area_id,
            tags=tags,
            keyword=request.keyword,
            limit=max(50, request.max_leads * 3),
        )

        data = await http.get_json(
            self._overpass,
            headers={"User-Agent": settings.nominatim_user_agent},
            params={"data": query},
        )
        if not isinstance(data, dict):
            log.warning("Overpass returned unexpected response.")
            return

        elements = data.get("elements") or []
        seen_names: set[str] = set()

        for el in elements:
            lead = self._element_to_lead(el, request)
            if lead is None:
                continue
            # Light in-source dedupe by name + city.
            key = (lead.company_name or "").lower().strip()
            if not key or key in seen_names:
                continue
            seen_names.add(key)
            yield lead

    # ------------------------------------------------------------------ #

    async def _resolve_area(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> int | None:
        """Resolve a user location into an Overpass `area` id."""
        q = request.location_string()
        if not q:
            return None

        params = {
            "q": q,
            "format": "json",
            "limit": "1",
            "addressdetails": "0",
        }
        data = await http.get_json(
            f"{self._nominatim}/search",
            params=params,
            headers={"User-Agent": settings.nominatim_user_agent},
        )
        if not isinstance(data, list) or not data:
            return None

        try:
            osm_type = str(data[0].get("osm_type", "")).lower()
            osm_id = int(data[0]["osm_id"])
        except (KeyError, ValueError, TypeError):
            return None

        # Overpass area id convention:
        #   way/relation -> area = osm_id + offset
        #   relation: +3_600_000_000
        #   way:      +2_400_000_000
        if osm_type == "relation":
            return osm_id + 3_600_000_000
        if osm_type == "way":
            return osm_id + 2_400_000_000
        # Nodes have no area; return None.
        return None

    def _tags_for_request(self, request: LeadRequest) -> list[tuple[str, str]]:
        if request.business_type and request.business_type in _OSM_TAG_MAP:
            return list(_OSM_TAG_MAP[request.business_type])
        return []

    def _build_overpass_query(
        self,
        *,
        area_id: int,
        tags: list[tuple[str, str]],
        keyword: str,
        limit: int,
    ) -> str:
        """Build an Overpass QL query scoped to ``area_id``."""
        # Build tag expressions
        tag_exprs: list[str] = []
        if tags:
            for k, v in tags:
                for kind in ("node", "way", "relation"):
                    tag_exprs.append(f'{kind}["{k}"="{v}"](area.searchArea);')
        else:
            # Name-based fallback (case-insensitive regex)
            safe = keyword.replace('"', "")
            for kind in ("node", "way", "relation"):
                tag_exprs.append(
                    f'{kind}["name"~"{safe}", i](area.searchArea);'
                )

        union = "\n  ".join(tag_exprs)
        query = (
            f"[out:json][timeout:25];\n"
            f"area({area_id})->.searchArea;\n"
            f"(\n  {union}\n);\n"
            f"out tags center {limit};\n"
        )
        return query

    def _element_to_lead(
        self,
        el: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        tags = el.get("tags") or {}
        name = clean_whitespace(tags.get("name"))
        if not name:
            return None

        website = normalize_url(
            tags.get("website") or tags.get("contact:website") or tags.get("url")
        )
        email = tags.get("email") or tags.get("contact:email")
        phone = tags.get("phone") or tags.get("contact:phone")

        # Build a readable address
        parts: list[str] = []
        for k in (
            "addr:housenumber",
            "addr:street",
            "addr:unit",
            "addr:suburb",
            "addr:city",
            "addr:postcode",
            "addr:country",
        ):
            v = tags.get(k)
            if v:
                parts.append(str(v))
        address = clean_whitespace(", ".join(parts)) if parts else None

        city = clean_whitespace(tags.get("addr:city") or request.city)
        country = clean_whitespace(tags.get("addr:country") or request.country)
        state = clean_whitespace(tags.get("addr:state") or request.state_or_region)

        category = _category_from_tags(tags) or request.business_type

        # Build an OSM source_url (useful for humans)
        osm_id = el.get("id")
        osm_kind = el.get("type")
        source_url = (
            f"https://www.openstreetmap.org/{osm_kind}/{osm_id}"
            if osm_id and osm_kind
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
            address=address,
            source_name=self.name,
            source_url=source_url,
        )


def _category_from_tags(tags: dict[str, Any]) -> str | None:
    for key in ("amenity", "office", "shop", "healthcare", "craft", "tourism", "leisure"):
        if tags.get(key):
            return f"{key}:{tags[key]}"
    return None
