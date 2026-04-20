"""Tests for FoursquareSource."""

from __future__ import annotations

import asyncio

import pytest

from app.models.lead_request import LeadRequest
from app.scraping.sources.foursquare_source import FoursquareSource
from app.tests.conftest import FakeHTTPClient


_SAMPLE = {
    "results": [
        {
            "fsq_id": "abc123",
            "name": "Acme Dental",
            "tel": "+12145551234",
            "website": "https://acme-dental.com",
            "email": "hello@acme-dental.com",
            "categories": [{"id": 17069, "name": "Dentist"}],
            "location": {
                "formatted_address": "100 Main St, Dallas, TX 75201",
                "locality": "Dallas",
                "region": "TX",
                "country": "US",
            },
            "social_media": {
                "facebook_id": "acmedental",
                "instagram": "acme.dental",
                "twitter": "acmedental",
            },
            "description": "Family dentistry.",
        },
        {
            "fsq_id": "def456",
            "name": "Smile Center",
            "categories": [{"name": "Dental Office"}],
            "location": {"locality": "Dallas", "country": "US"},
            "social_media": {},
        },
        # Missing name => skipped.
        {"fsq_id": "xyz"},
    ]
}


async def _run(src, req, http):
    return [lead async for lead in src.search(req, http)]


def test_foursquare_rejects_empty_key():
    with pytest.raises(ValueError):
        FoursquareSource("")


def test_foursquare_parses_and_sends_raw_auth_header():
    req = LeadRequest(
        keyword="dentist",
        business_type="dentist",
        city="Dallas",
        country="USA",
    )
    http = FakeHTTPClient(json_responses=[_SAMPLE])
    src = FoursquareSource("raw-fsq-key")

    leads = asyncio.run(_run(src, req, http))
    assert len(leads) == 2

    a = leads[0]
    assert a.company_name == "Acme Dental"
    assert a.website == "https://acme-dental.com/"
    assert a.email == "hello@acme-dental.com"
    assert a.phone == "+12145551234"
    assert a.category == "Dentist"
    assert a.facebook_url == "https://www.facebook.com/acmedental"
    assert a.instagram_url == "https://www.instagram.com/acme.dental"
    assert a.twitter_url == "https://twitter.com/acmedental"
    assert a.description == "Family dentistry."
    assert a.source_name == "foursquare"
    assert a.source_url == "https://foursquare.com/v/abc123"

    call = http.calls[0]
    # Foursquare uses the raw key, NOT "Bearer <key>".
    assert call["headers"]["Authorization"] == "raw-fsq-key"
    assert call["params"]["near"].startswith("Dallas")
    assert call["params"]["query"] == "dentist"
    assert "fields" in call["params"]


def test_foursquare_skipped_without_location():
    req = LeadRequest(keyword="dentist")
    http = FakeHTTPClient()
    src = FoursquareSource("raw-fsq-key")

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
    assert http.calls == []
