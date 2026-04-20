"""Tests for GoogleMapsSource (best-effort local-pack scraper)."""

from __future__ import annotations

import asyncio

from app.models.lead_request import LeadRequest
from app.scraping.sources.google_maps_source import GoogleMapsSource
from app.tests.conftest import FakeHTTPClient


# Synthetic HTML that mimics the Google local-pack card layout.  We don't try
# to faithfully replicate Google's real output (which is volatile); we only
# verify that our parser handles the selectors/text structure it claims to.
_SAMPLE_HTML = """
<html><body>
  <div class="VkpGBb">
    <div class="rllt__details">
      <div class="dbg0pd"><span class="OSrXXb">Acme Dental</span></div>
      <div>4.6 (123) &middot; Dentist</div>
      <div>100 Main St &middot; (214) 555-1234</div>
    </div>
  </div>
  <div class="VkpGBb">
    <div class="rllt__details">
      <div class="dbg0pd"><span class="OSrXXb">Smile Center</span></div>
      <div>Dental Office</div>
      <div>200 Oak Ave</div>
    </div>
  </div>
  <div class="VkpGBb">
    <!-- malformed: no name div -->
    <div class="rllt__details"><div>Orphan line</div></div>
  </div>
</body></html>
"""


async def _run(src, req, http):
    return [lead async for lead in src.search(req, http)]


def test_google_maps_parses_local_pack_cards():
    req = LeadRequest(
        keyword="dentist",
        city="Dallas",
        state_or_region="TX",
        country="USA",
    )
    http = FakeHTTPClient(text_responses=[_SAMPLE_HTML])
    src = GoogleMapsSource()

    leads = asyncio.run(_run(src, req, http))

    assert len(leads) == 2
    a = leads[0]
    assert a.company_name == "Acme Dental"
    assert a.category == "Dentist"
    assert a.phone and "214" in a.phone
    assert a.address and "Main St" in a.address
    assert a.source_name == "google_maps"
    assert a.city == "Dallas"

    b = leads[1]
    assert b.company_name == "Smile Center"
    assert b.address == "200 Oak Ave"


def test_google_maps_sends_browser_headers():
    req = LeadRequest(keyword="cafe", city="Austin", country="USA")
    http = FakeHTTPClient(text_responses=[_SAMPLE_HTML])
    src = GoogleMapsSource()

    asyncio.run(_run(src, req, http))

    call = http.calls[0]
    assert call["url"].startswith("https://www.google.com/search")
    assert "tbm=lcl" in call["url"]
    assert "Mozilla" in call["headers"]["User-Agent"]


def test_google_maps_empty_response_yields_nothing():
    req = LeadRequest(keyword="dentist", city="Dallas")
    http = FakeHTTPClient(text_responses=[None])
    src = GoogleMapsSource()

    leads = asyncio.run(_run(src, req, http))
    assert leads == []


def test_google_maps_unparseable_html_yields_nothing():
    req = LeadRequest(keyword="dentist", city="Dallas")
    # Page with no VkpGBb / rllt__details markers -> nothing parses.
    http = FakeHTTPClient(text_responses=["<html><body>no results</body></html>"])
    src = GoogleMapsSource()

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
