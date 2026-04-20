"""Tests for the rule-based request parser."""

from __future__ import annotations

import pytest

from app.parsing.request_parser import ParseError, parse_request


def test_full_request_parsed():
    r = parse_request("Find 50 dentists in Dallas with email and website")
    assert r.keyword == "dentists"
    assert r.business_type == "dentist"
    assert r.industry == "healthcare"
    assert r.city == "Dallas"
    assert r.state_or_region == "Texas"
    assert r.country == "USA"
    assert r.max_leads == 50
    assert r.email_required is True
    assert r.website_required is True
    assert r.phone_required is False
    assert r.social_required is False


def test_uk_request():
    r = parse_request("Need real estate agents in London")
    assert r.business_type == "real_estate_agency"
    assert r.city == "London"
    assert r.country == "United Kingdom"


def test_berlin_with_phone():
    r = parse_request("Scrape software companies in Berlin with phone numbers")
    assert r.business_type == "it_company"
    assert r.city == "Berlin"
    assert r.country == "Germany"
    assert r.phone_required is True


def test_default_max_leads(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "default_max_leads", 20)
    r = parse_request("Find dentists in Dallas")
    assert r.max_leads == 20


def test_max_leads_capped(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_leads_limit", 100)
    r = parse_request("Find 5000 dentists in Dallas")
    assert r.max_leads == 100


def test_missing_location_raises():
    with pytest.raises(ParseError) as excinfo:
        parse_request("Find 10 dentists")
    messages = [i.field for i in excinfo.value.issues]
    assert "location" in messages


def test_missing_keyword_raises():
    with pytest.raises(ParseError):
        parse_request("Find 10 in Dallas")


def test_paris_infers_france():
    r = parse_request("Find restaurants in Paris")
    assert r.city == "Paris"
    assert r.country == "France"


def test_country_alias():
    r = parse_request("Find dentists in New York, USA")
    assert r.country == "USA"
    assert r.city == "New York"


def test_social_required():
    r = parse_request("Find 30 marketing agencies in New York with social media")
    assert r.social_required is True
    assert r.business_type == "marketing_agency"
