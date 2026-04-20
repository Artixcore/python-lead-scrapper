"""Wikidata SPARQL source.

Queries the public Wikidata SPARQL endpoint for organizations located in the
requested city/region.  Coverage skews toward mid-to-large notable entities
(large restaurant chains, hospitals, banks, universities...) so this is
mainly a *supplement* to OSM/Yelp/etc. for bigger targets, not a replacement.

No API key required.  Wikidata asks callers to send a descriptive User-Agent
and be gentle (we use the existing rate limiter).
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


# Minimal business-type -> Wikidata QID map.  Each entry is a list of QIDs we
# will OR together (via wdt:P31/wdt:P279*) so both the class itself and its
# subclasses match.  Unknown types fall back to "business" (Q4830453).
_WD_TYPE_MAP: dict[str, list[str]] = {
    "restaurant": ["Q11707"],
    "cafe": ["Q30022"],
    "bar": ["Q187456"],
    "hotel": ["Q27686"],
    "hospital": ["Q16917"],
    "clinic": ["Q7257872"],
    "pharmacy": ["Q91917"],
    "bank": ["Q22687"],
    "university": ["Q3918"],
    "school": ["Q3914"],
    "library": ["Q7075"],
    "museum": ["Q33506"],
    "law_firm": ["Q613142"],
    "lawyer": ["Q613142"],
    "it_company": ["Q880331"],
    "accountant": ["Q3044918"],
}
_DEFAULT_QIDS = ["Q4830453"]  # business


class WikidataSource(BaseSource):
    """Wikidata SPARQL adapter."""

    name = "wikidata"

    def __init__(self) -> None:
        self._endpoint = settings.wikidata_sparql_url

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        if not request.has_location():
            # Without a location the query is unbounded and times out.
            return

        qids = _WD_TYPE_MAP.get(request.business_type or "", _DEFAULT_QIDS)
        query = _build_sparql(
            type_qids=qids,
            location=request.location_string(),
            language=self._query_language(request),
            limit=min(50, max(10, request.max_leads * 2)),
        )

        data = await http.get_json(
            self._endpoint,
            params={"query": query, "format": "json"},
            headers={
                "User-Agent": settings.nominatim_user_agent,
                "Accept": "application/sparql-results+json",
            },
        )
        if not isinstance(data, dict):
            log.debug("Wikidata: unexpected response type.")
            return

        bindings = (data.get("results") or {}).get("bindings") or []
        seen: set[str] = set()

        for row in bindings:
            lead = self._row_to_lead(row, request)
            if lead is None:
                continue
            key = (lead.company_name or "").lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            yield lead

    # ------------------------------------------------------------------ #

    def _query_language(self, request: LeadRequest) -> str:
        # We'd love to inspect the country to pick a local language, but
        # English is by far the most populated label language in Wikidata
        # and matches our other sources.
        return "en"

    def _row_to_lead(
        self,
        row: dict[str, Any],
        request: LeadRequest,
    ) -> Lead | None:
        def val(k: str) -> str | None:
            cell = row.get(k)
            if isinstance(cell, dict):
                v = cell.get("value")
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return None

        name = clean_whitespace(val("label"))
        if not name:
            return None

        website = normalize_url(val("website"))
        item = val("item")

        return Lead(
            company_name=name,
            category=val("typeLabel") or request.business_type,
            website=website,
            city=clean_whitespace(val("locLabel")) or request.city,
            state_or_region=request.state_or_region,
            country=clean_whitespace(val("countryLabel")) or request.country,
            description=clean_whitespace(val("description")),
            source_name=self.name,
            source_url=item,
        )


def _build_sparql(
    *,
    type_qids: list[str],
    location: str,
    language: str,
    limit: int,
) -> str:
    """Construct a compact SPARQL query.

    We search for any item whose type (P31) is (a subclass of) one of
    ``type_qids`` and whose location (P131 "located in the administrative
    territorial entity", walking up the hierarchy) has a label that matches
    ``location`` case-insensitively.  Fields returned: item, label, optional
    website/description/country/type labels.
    """
    # OR of VALUES for type QIDs: "VALUES ?type { wd:Q11707 wd:Q30022 }"
    values_line = "VALUES ?type { " + " ".join(f"wd:{q}" for q in type_qids) + " }"
    # Escape any stray quote in the location string.
    safe_loc = location.replace('"', r"\"")

    return f"""
SELECT ?item ?label ?description ?website ?loc ?locLabel ?country ?countryLabel ?type ?typeLabel
WHERE {{
  {values_line}
  ?item wdt:P31/wdt:P279* ?type .
  ?item wdt:P131* ?loc .
  ?loc rdfs:label ?locLabel .
  FILTER(LANG(?locLabel) = "{language}")
  FILTER(CONTAINS(LCASE(?locLabel), LCASE("{safe_loc}")))
  ?item rdfs:label ?label .
  FILTER(LANG(?label) = "{language}")
  OPTIONAL {{ ?item wdt:P856 ?website . }}
  OPTIONAL {{ ?item wdt:P17 ?country . ?country rdfs:label ?countryLabel .
             FILTER(LANG(?countryLabel) = "{language}") }}
  OPTIONAL {{ ?type rdfs:label ?typeLabel . FILTER(LANG(?typeLabel) = "{language}") }}
  OPTIONAL {{ ?item schema:description ?description .
             FILTER(LANG(?description) = "{language}") }}
}}
LIMIT {int(limit)}
""".strip()
