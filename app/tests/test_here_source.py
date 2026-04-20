"""Tests for HereSource."""

from __future__ import annotations

import asyncio

import pytest

from app.models.lead_request import LeadRequest
from app.scraping.sources import _geocoder
from app.scraping.sources.here_source import HereSource
from app.tests.conftest import FakeHTTPClient


_GEOCODE_RESP = [{"lat": "32.7767", "lon": "-96.7970"}]

_DISCOVER_RESP = {
    "items": [
        {
            "title": "Acme Dental",
            "address": {
                "label": "100 Main St, Dallas, TX 75201",
                "city": "Dallas",
                "state": "Texas",
                "stateCode": "TX",
                "countryName": "United States",
            },
            "contacts": [
                {
                    "phone": [{"value": "+12145551234"}],
                    "www": [{"value": "https://acme-dental.com"}],
                    "email": [{"value": "hello@acme-dental.com"}],
                }
            ],
            "categories": [
                {"id": "600-6900-0000", "name": "Dentist", "primary": True},
                {"id": "600-0000-0000", "name": "Business"},
            ],
        },
        {
            "title": "Smile Center",
            "address": {"label": "200 Oak Ave, Dallas, TX"},
            "contacts": [],
            "categories": [{"name": "Dental Office", "primary": True}],
        },
    ]
}


async def _run(src, req, http):
    return [lead async for lead in src.search(req, http)]


def test_here_rejects_empty_key():
    with pytest.raises(ValueError):
        HereSource("")


def test_here_parses_items_and_geocodes_once():
    _geocoder.clear_cache()

    req = LeadRequest(
        keyword="dentist",
        city="Dallas",
        state_or_region="TX",
        country="USA",
    )
    # First call = Nominatim geocode; second = HERE discover.
    http = FakeHTTPClient(json_responses=[_GEOCODE_RESP, _DISCOVER_RESP])
    src = HereSource("test-key")

    leads = asyncio.run(_run(src, req, http))

    assert len(leads) == 2
    a = leads[0]
    assert a.company_name == "Acme Dental"
    assert a.website == "https://acme-dental.com/"
    assert a.email == "hello@acme-dental.com"
    assert a.phone == "+12145551234"
    assert a.category == "Dentist"
    assert a.city == "Dallas"
    assert a.country == "United States"
    assert a.source_name == "here"

    # Second HTTP call should include apiKey + at=lat,lon.
    discover_call = http.calls[1]
    assert "apiKey" in discover_call["params"]
    assert "at" in discover_call["params"]
    assert discover_call["params"]["at"].startswith("32.776")


def test_here_geocode_cache_reused_across_calls():
    _geocoder.clear_cache()

    req = LeadRequest(keyword="dentist", city="Dallas", country="USA")

    # Run 1: geocode + discover.
    http1 = FakeHTTPClient(json_responses=[_GEOCODE_RESP, _DISCOVER_RESP])
    src = HereSource("test-key")
    asyncio.run(_run(src, req, http1))
    assert len(http1.calls) == 2

    # Run 2: same location => geocoder cache hit, so only discover is called.
    http2 = FakeHTTPClient(json_responses=[_DISCOVER_RESP])
    asyncio.run(_run(src, req, http2))
    assert len(http2.calls) == 1
    assert "discover.search.hereapi.com" in http2.calls[0]["url"]


def test_here_skipped_when_geocode_fails():
    _geocoder.clear_cache()
    req = LeadRequest(keyword="dentist", city="Nowhereville", country="Atlantis")
    # Geocoder returns empty list -> no coords -> no discover call.
    http = FakeHTTPClient(json_responses=[[]])
    src = HereSource("test-key")

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
    # Only the geocode attempt was made.
    assert len(http.calls) == 1
