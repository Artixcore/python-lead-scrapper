"""Tests for NominatimPOISource."""

from __future__ import annotations

import asyncio

from app.models.lead_request import LeadRequest
from app.scraping.sources.nominatim_poi_source import NominatimPOISource
from app.tests.conftest import FakeHTTPClient


_SAMPLE = [
    {
        "osm_type": "node",
        "osm_id": 1,
        "display_name": "Acme Dental, Main St, Dallas, Texas, USA",
        "category": "amenity",
        "type": "dentist",
        "namedetails": {"name": "Acme Dental"},
        "address": {
            "house_number": "100",
            "road": "Main St",
            "city": "Dallas",
            "state": "Texas",
            "country": "United States",
            "postcode": "75201",
        },
        "extratags": {
            "website": "https://acme-dental.com",
            "phone": "+1 214-555-1234",
            "email": "hello@acme-dental.com",
        },
    },
    {
        "osm_type": "way",
        "osm_id": 2,
        "display_name": "Smile Center, Oak Ave, Dallas, Texas, USA",
        "category": "amenity",
        "type": "dentist",
        "namedetails": {"name": "Smile Center"},
        "address": {"city": "Dallas", "country": "United States"},
        "extratags": {},
    },
    # Missing name -> should be skipped.
    {"osm_type": "node", "osm_id": 3, "namedetails": {}, "address": {}},
]


async def _run(src: NominatimPOISource, req: LeadRequest, http: FakeHTTPClient):
    return [lead async for lead in src.search(req, http)]  # type: ignore[arg-type]


def test_nominatim_poi_parses_basic_fields():
    req = LeadRequest(keyword="dentist", city="Dallas", country="USA")
    http = FakeHTTPClient(json_responses=[_SAMPLE])
    src = NominatimPOISource()

    leads = asyncio.run(_run(src, req, http))

    assert len(leads) == 2
    a = leads[0]
    assert a.company_name == "Acme Dental"
    assert a.website == "https://acme-dental.com/"
    assert a.email == "hello@acme-dental.com"
    assert a.phone == "+1 214-555-1234"
    assert a.city == "Dallas"
    assert a.state_or_region == "Texas"
    assert a.country == "United States"
    assert "100" in (a.address or "")
    assert a.source_name == "nominatim_poi"
    assert a.source_url == "https://www.openstreetmap.org/node/1"
    assert a.category == "amenity:dentist"


def test_nominatim_poi_sends_query_and_headers():
    req = LeadRequest(keyword="cafe", city="Austin", country="USA")
    http = FakeHTTPClient(json_responses=[[]])
    src = NominatimPOISource()

    asyncio.run(_run(src, req, http))

    call = http.calls[0]
    assert call["url"].endswith("/search")
    assert "cafe" in call["params"]["q"]
    assert "Austin" in call["params"]["q"]
    assert call["params"]["format"] == "jsonv2"
    assert "User-Agent" in call["headers"]


def test_nominatim_poi_handles_empty_response():
    req = LeadRequest(keyword="dentist", city="Dallas")
    http = FakeHTTPClient(json_responses=[None])
    src = NominatimPOISource()

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
