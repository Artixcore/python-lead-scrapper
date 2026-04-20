"""Tests for YelpSource."""

from __future__ import annotations

import asyncio

import pytest

from app.models.lead_request import LeadRequest
from app.scraping.sources.yelp_source import YelpSource
from app.tests.conftest import FakeHTTPClient


_SAMPLE = {
    "businesses": [
        {
            "id": "acme-dental-dallas",
            "name": "Acme Dental",
            "url": "https://www.yelp.com/biz/acme-dental-dallas",
            "display_phone": "+1 214-555-1234",
            "phone": "+12145551234",
            "categories": [{"alias": "dentists", "title": "Dentists"}],
            "location": {
                "address1": "100 Main St",
                "city": "Dallas",
                "state": "TX",
                "country": "US",
                "display_address": ["100 Main St", "Dallas, TX 75201"],
            },
        },
        {
            "id": "smile-center-dallas",
            "name": "Smile Center",
            "url": "https://www.yelp.com/biz/smile-center-dallas",
            "display_phone": "",
            "categories": [{"alias": "dentists", "title": "Dentists"}],
            "location": {
                "city": "Dallas",
                "country": "US",
                "display_address": ["200 Oak Ave", "Dallas, TX"],
            },
        },
    ]
}


async def _run(src, req, http):
    return [lead async for lead in src.search(req, http)]


def test_yelp_rejects_empty_key():
    with pytest.raises(ValueError):
        YelpSource("")


def test_yelp_parses_and_sends_auth_header():
    req = LeadRequest(
        keyword="dentist",
        business_type="dentist",
        city="Dallas",
        state_or_region="TX",
        country="USA",
    )
    http = FakeHTTPClient(json_responses=[_SAMPLE])
    src = YelpSource("test-key")

    leads = asyncio.run(_run(src, req, http))

    assert len(leads) == 2
    a = leads[0]
    assert a.company_name == "Acme Dental"
    assert a.source_name == "yelp"
    assert a.phone == "+1 214-555-1234"
    assert a.city == "Dallas"
    assert a.country == "US"
    assert a.category == "Dentists"
    assert "100 Main St" in (a.address or "")

    # Auth header + categories param sent
    call = http.calls[0]
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["params"]["categories"] == "dentists"
    assert call["params"]["location"].startswith("Dallas")


def test_yelp_skipped_without_location():
    req = LeadRequest(keyword="dentist")
    http = FakeHTTPClient()
    src = YelpSource("test-key")

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
    assert http.calls == []
