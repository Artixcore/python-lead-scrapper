"""Tests for the content extractors."""

from __future__ import annotations

from app.scraping.extractors.contact_page_finder import find_contact_pages
from app.scraping.extractors.email_extractor import extract_emails
from app.scraping.extractors.phone_extractor import extract_phones
from app.scraping.extractors.social_extractor import extract_social_links


HTML = """
<html>
<head><title>Acme Dental</title>
  <meta name="description" content="Friendly family dentistry in Dallas, TX.">
</head>
<body>
  <a href="mailto:hello@acme-dental.com">Email us</a>
  <p>Or reach us at info (at) acme-dental.com</p>
  <a href="tel:+1-214-555-1234">Call</a>
  <p>Office: (214) 555-9876</p>
  <a href="https://facebook.com/acmedental">Facebook</a>
  <a href="https://www.linkedin.com/company/acme-dental/">LinkedIn</a>
  <a href="/contact-us">Contact us</a>
  <a href="/about">About</a>
  <a href="/blog/post-1">Blog</a>
  <img src="signature.png" alt="sig">
  <a href="mailto:logo.png@example.com">bad</a>
</body>
</html>
"""


def test_extract_emails_picks_real():
    emails = extract_emails(HTML)
    assert "hello@acme-dental.com" in emails
    assert "info@acme-dental.com" in emails
    # junk emails filtered out
    assert not any("example.com" in e for e in emails)
    assert not any(".png" in e for e in emails)


def test_extract_phones_us_numbers():
    phones = extract_phones(HTML, default_region="US")
    assert "+12145551234" in phones
    # (214) 555-9876 => +12145559876
    assert any(p.startswith("+1214") for p in phones)


def test_extract_social_links():
    socials = extract_social_links(HTML, base_url="https://acme-dental.com")
    assert socials.get("facebook_url") == "https://facebook.com/acmedental"
    assert socials.get("linkedin_url") == "https://www.linkedin.com/company/acme-dental/"


def test_contact_page_finder():
    pages = find_contact_pages(HTML, base_url="https://acme-dental.com")
    assert any("contact" in p for p in pages)
    assert any("about" in p for p in pages)
    # blog should not be a contact page candidate
    assert not any("blog" in p for p in pages)


def test_extract_emails_empty_input():
    assert extract_emails("") == []
    assert extract_phones("", default_region="US") == []
