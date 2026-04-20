"""Enrich a ``Lead`` by visiting its website and extracting contact data."""

from __future__ import annotations

from app.logging_config import get_logger
from app.models.lead import Lead
from app.scraping.base import HTTPClient
from app.scraping.extractors import (
    extract_emails,
    extract_phones,
    extract_social_links,
    find_contact_pages,
)
from app.services.cache_service import CacheService
from app.utils.html_tools import make_soup
from app.utils.text_tools import clean_whitespace, truncate
from app.utils.url_tools import normalize_url, root_url

log = get_logger(__name__)


# ISO country name -> ISO 3166-1 alpha-2 for phonenumbers default region.
_COUNTRY_TO_REGION: dict[str, str] = {
    "USA": "US",
    "United States": "US",
    "United States of America": "US",
    "Canada": "CA",
    "United Kingdom": "GB",
    "UK": "GB",
    "France": "FR",
    "Germany": "DE",
    "Spain": "ES",
    "Italy": "IT",
    "Netherlands": "NL",
    "Belgium": "BE",
    "Austria": "AT",
    "Switzerland": "CH",
    "Ireland": "IE",
    "Portugal": "PT",
    "Sweden": "SE",
    "Denmark": "DK",
    "Norway": "NO",
    "Finland": "FI",
    "Poland": "PL",
    "Czechia": "CZ",
    "Japan": "JP",
    "South Korea": "KR",
    "Singapore": "SG",
    "Hong Kong": "HK",
    "Australia": "AU",
    "India": "IN",
    "Mexico": "MX",
    "Brazil": "BR",
    "Argentina": "AR",
    "United Arab Emirates": "AE",
}


def _default_region(country: str | None) -> str | None:
    if not country:
        return None
    return _COUNTRY_TO_REGION.get(country.strip())


class WebsiteEnricher:
    """Enriches leads by fetching their website + contact/about pages."""

    name = "website_enricher"

    def __init__(self, cache: CacheService | None = None) -> None:
        self._cache = cache

    async def enrich(self, lead: Lead, http: HTTPClient) -> Lead:
        """Return a copy of ``lead`` with extra fields populated (if possible)."""
        if not lead.website:
            return lead

        base = root_url(lead.website) or normalize_url(lead.website)
        if not base:
            return lead

        region = _default_region(lead.country)

        homepage = await self._fetch(base, http)
        if homepage:
            self._merge_extracted(lead, homepage, base, region)

        # Follow up with a couple of contact/about pages.
        if homepage:
            contact_pages = find_contact_pages(homepage, base, limit=2)
            if contact_pages and not lead.contact_page:
                lead.contact_page = contact_pages[0]

            for url in contact_pages:
                html = await self._fetch(url, http)
                if html:
                    self._merge_extracted(lead, html, url, region)
                # Stop early if we already have email + phone
                if lead.email and lead.phone:
                    break

        return lead

    # ------------------------------------------------------------------ #

    async def _fetch(self, url: str, http: HTTPClient) -> str | None:
        if self._cache:
            cached = await self._cache.get_page(url)
            if cached is not None:
                return cached

        html = await http.get_text(url)
        if self._cache and html is not None:
            try:
                await self._cache.set_page(url, html)
            except Exception:  # pragma: no cover
                log.debug("Cache write failed for %s", url)
        return html

    def _merge_extracted(
        self,
        lead: Lead,
        html: str,
        base_url: str,
        region: str | None,
    ) -> None:
        """Extract data from ``html`` and populate missing fields on ``lead``."""
        try:
            if not lead.email:
                emails = extract_emails(html)
                if emails:
                    lead.email = emails[0]

            if not lead.phone:
                phones = extract_phones(html, default_region=region)
                if phones:
                    lead.phone = phones[0]

            socials = extract_social_links(html, base_url=base_url)
            if socials.get("linkedin_url") and not lead.linkedin_url:
                lead.linkedin_url = socials["linkedin_url"]
            if socials.get("facebook_url") and not lead.facebook_url:
                lead.facebook_url = socials["facebook_url"]
            if socials.get("instagram_url") and not lead.instagram_url:
                lead.instagram_url = socials["instagram_url"]
            if socials.get("twitter_url") and not lead.twitter_url:
                lead.twitter_url = socials["twitter_url"]

            if not lead.description:
                lead.description = _extract_description(html)
        except Exception as e:  # pragma: no cover
            log.debug("Enricher extractor error for %s: %s", base_url, e)


def _extract_description(html: str) -> str | None:
    """Pull a short description from meta tags / title."""
    try:
        soup = make_soup(html)
    except Exception:
        return None

    for selector in [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ]:
        tag = soup.find("meta", attrs=selector)
        if tag and tag.get("content"):
            desc = clean_whitespace(tag["content"])
            if desc:
                return truncate(desc, 240)

    if soup.title and soup.title.string:
        return truncate(clean_whitespace(soup.title.string), 240)

    return None
