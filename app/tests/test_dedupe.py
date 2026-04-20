"""Tests for the dedupe service."""

from __future__ import annotations

from app.models.lead import Lead
from app.services.dedupe_service import DedupeService


def _make(
    name: str,
    *,
    website: str | None = None,
    city: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    email: str | None = None,
) -> Lead:
    return Lead(
        company_name=name,
        website=website,
        city=city,
        phone=phone,
        address=address,
        email=email,
    )


def test_dedupe_by_domain():
    svc = DedupeService()
    a = _make("Acme Dental", website="https://acme-dental.com/")
    b = _make("Acme Dental LLC", website="https://acme-dental.com/contact")
    leads = svc.dedupe([a, b])
    assert len(leads) == 1


def test_dedupe_by_name_and_city():
    svc = DedupeService()
    a = _make("Acme Dental", city="Dallas")
    b = _make("ACME   Dental", city="dallas")
    leads = svc.dedupe([a, b])
    assert len(leads) == 1


def test_merge_fills_missing_fields():
    svc = DedupeService()
    a = _make("Acme Dental", city="Dallas")
    b = _make(
        "Acme Dental",
        city="Dallas",
        website="https://acme-dental.com/",
        email="hi@acme-dental.com",
        phone="+12145551234",
    )
    leads = svc.dedupe([a, b])
    assert len(leads) == 1
    merged = leads[0]
    assert merged.website == "https://acme-dental.com/"
    assert merged.email == "hi@acme-dental.com"
    assert merged.phone == "+12145551234"


def test_unique_leads_kept():
    svc = DedupeService()
    a = _make("Acme Dental", city="Dallas")
    b = _make("Smile Center", city="Dallas")
    c = _make("Pearl Dental", city="Austin")
    leads = svc.dedupe([a, b, c])
    assert len(leads) == 3


def test_empty_input():
    assert DedupeService().dedupe([]) == []
