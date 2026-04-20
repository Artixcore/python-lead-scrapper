"""Google Maps / Local Search scraper.

WARNING
=======

Google's Terms of Service forbid automated scraping of Google Search and
Google Maps.  Google also rotates HTML classes, inserts CAPTCHAs, and soft-
blocks IPs that send too many requests.  This source is therefore:

- **Disabled by default** (opt-in via ``ENABLE_GOOGLE_MAPS=true``).
- **Best-effort**: if the HTML format drifts, this source returns zero
  results and logs a warning rather than raising.
- **Subject to rate limits** through the shared ``HTTPClient`` limiter.

Prefer the official Google Places API or the other providers in this project
(Yelp, HERE, Foursquare) whenever possible.

Implementation notes
====================

We hit ``https://www.google.com/search?tbm=lcl&q=...`` (the "local pack"
results page) rather than Maps itself, because its HTML is flatter and
easier to parse.  Each result is a card under ``div.VkpGBb`` (historically
stable); we read the business name from ``div.dbg0pd`` and subsequent
siblings for category/address/phone.
"""

from __future__ import annotations

import re
from typing import AsyncIterator
from urllib.parse import quote_plus

from bs4 import Tag

from app.config import settings
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.scraping.base import BaseSource, HTTPClient
from app.utils.html_tools import make_soup
from app.utils.text_tools import clean_whitespace

log = get_logger(__name__)


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")


class GoogleMapsSource(BaseSource):
    """Google local search scraper (fragile; opt-in)."""

    name = "google_maps"

    def __init__(self, *, hl: str | None = None) -> None:
        self._hl = (hl or settings.google_maps_hl or "en").strip() or "en"

    async def search(
        self,
        request: LeadRequest,
        http: HTTPClient,
    ) -> AsyncIterator[Lead]:
        query = self._build_query(request)
        if not query:
            return

        url = (
            "https://www.google.com/search"
            f"?tbm=lcl&hl={quote_plus(self._hl)}&q={quote_plus(query)}"
        )
        html = await http.get_text(
            url,
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Accept-Language": f"{self._hl},en;q=0.8",
            },
        )
        if not html:
            log.warning("GoogleMapsSource: empty response for %r.", query)
            return

        leads = self._parse_results(html, request)
        if not leads:
            # Log once per job so operators notice layout drift.
            log.warning(
                "GoogleMapsSource: 0 leads parsed for %r (layout change or CAPTCHA?).",
                query,
            )
            return

        seen: set[str] = set()
        for lead in leads:
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
            parts.append(f"in {loc}")
        return " ".join(parts).strip()

    def _parse_results(
        self,
        html: str,
        request: LeadRequest,
    ) -> list[Lead]:
        """Parse the local-pack HTML, returning a list of leads."""
        soup = make_soup(html)
        results: list[Lead] = []

        # Each result card. Google has historically used "VkpGBb" for the
        # outer clickable container; fall back to "rllt__details" which wraps
        # the text content on simpler layouts.
        cards = soup.select("div.VkpGBb") or soup.select("div.rllt__details")

        for card in cards:
            lead = self._card_to_lead(card, request)
            if lead is not None:
                results.append(lead)

        return results

    def _card_to_lead(
        self,
        card: Tag,
        request: LeadRequest,
    ) -> Lead | None:
        # Business name
        name_el = card.select_one("div.dbg0pd") or card.select_one("span.OSrXXb")
        name = clean_whitespace(name_el.get_text(" ", strip=True)) if name_el else None
        if not name:
            return None

        # Category: sibling line typically inside "rllt__details" wrapper.
        # The structure is usually:
        #   <div class="rllt__details">
        #     <div class="dbg0pd">Name</div>
        #     <div>Rating · Category</div>
        #     <div>Address · Phone</div>
        #   </div>
        details = card if "rllt__details" in (card.get("class") or []) else card.select_one("div.rllt__details")
        category = None
        address = None
        phone = None

        if details is not None:
            lines: list[str] = []
            for div in details.find_all("div", recursive=False):
                txt = clean_whitespace(div.get_text(" ", strip=True))
                if txt and txt != name:
                    lines.append(txt)

            # Heuristics: first line after the name usually contains the
            # category (separated by "·" or "-"); last line usually contains
            # the address; phones look like phone numbers.
            if lines:
                first = lines[0]
                # "4.6 (123) · Dentist" or "Dentist"
                category = first.split("\u00b7")[-1].strip() or first
            for line in lines[1:]:
                m = _PHONE_RE.search(line)
                if m and not phone:
                    phone = clean_whitespace(m.group(0))
                # Treat any non-phone line as a potential address.
                if address is None and (not m or line != m.group(0)):
                    # Strip an embedded phone from the address if both appear
                    # on the same line.
                    cleaned = line
                    if m:
                        cleaned = cleaned.replace(m.group(0), "").strip(" \u00b7-")
                    address = clean_whitespace(cleaned)

        return Lead(
            company_name=name,
            category=category or request.business_type,
            website=None,  # Google hides the business URL behind a redirect;
                           # the website enricher will discover it later.
            email=None,
            phone=phone,
            city=request.city,
            state_or_region=request.state_or_region,
            country=request.country,
            address=address,
            source_name=self.name,
            source_url=None,
        )
