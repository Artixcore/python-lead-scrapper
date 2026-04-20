"""Tests for WikidataSource."""

from __future__ import annotations

import asyncio

from app.models.lead_request import LeadRequest
from app.scraping.sources.wikidata_source import WikidataSource
from app.tests.conftest import FakeHTTPClient


def _bind(**kv):
    return {k: {"type": "literal", "value": v} for k, v in kv.items()}


_SAMPLE = {
    "head": {"vars": ["item", "label", "website"]},
    "results": {
        "bindings": [
            _bind(
                item="http://www.wikidata.org/entity/Q123",
                label="Acme Restaurant",
                website="https://acme.example",
                locLabel="Dallas",
                countryLabel="United States",
                typeLabel="restaurant",
                description="Family restaurant.",
            ),
            _bind(
                item="http://www.wikidata.org/entity/Q456",
                label="Bravo Bistro",
                locLabel="Dallas",
                countryLabel="United States",
                typeLabel="restaurant",
            ),
            # No label -> skipped
            _bind(item="http://www.wikidata.org/entity/Q789"),
        ]
    },
}


async def _run(src: WikidataSource, req: LeadRequest, http: FakeHTTPClient):
    return [lead async for lead in src.search(req, http)]  # type: ignore[arg-type]


def test_wikidata_parses_bindings():
    req = LeadRequest(
        keyword="restaurant",
        business_type="restaurant",
        city="Dallas",
        country="United States",
    )
    http = FakeHTTPClient(json_responses=[_SAMPLE])
    src = WikidataSource()

    leads = asyncio.run(_run(src, req, http))
    assert len(leads) == 2
    a = leads[0]
    assert a.company_name == "Acme Restaurant"
    assert a.website == "https://acme.example/"
    assert a.city == "Dallas"
    assert a.country == "United States"
    assert a.category == "restaurant"
    assert a.description == "Family restaurant."
    assert a.source_url == "http://www.wikidata.org/entity/Q123"
    assert a.source_name == "wikidata"


def test_wikidata_skipped_when_no_location():
    req = LeadRequest(keyword="restaurant")  # no city/region/country
    http = FakeHTTPClient()
    src = WikidataSource()

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
    # Should not have made any HTTP call.
    assert http.calls == []


def test_wikidata_handles_malformed_response():
    req = LeadRequest(keyword="restaurant", city="Dallas")
    http = FakeHTTPClient(json_responses=["unexpected string"])
    src = WikidataSource()

    leads = asyncio.run(_run(src, req, http))
    assert leads == []
