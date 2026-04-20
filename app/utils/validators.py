"""Validators for emails, phones, URLs, etc."""

from __future__ import annotations

import re

import phonenumbers

from app.utils.url_tools import is_http_url

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

# Emails that often appear in scraped markup but aren't real contacts.
_EMAIL_JUNK_SUBSTRINGS = (
    "example.com",
    "example.org",
    "sentry.io",
    "wixpress.com",
    "@sentry",
    "email@",
    "name@",
    "test@",
    "user@",
    "no-reply",
    "noreply",
    "donotreply",
    "do-not-reply",
)

_EMAIL_JUNK_EXT = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
)


def is_valid_email(email: str | None) -> bool:
    """Return True if ``email`` looks like a real contact email."""
    if not email:
        return False
    e = email.strip().lower()
    if not _EMAIL_RE.match(e):
        return False
    if any(ext in e for ext in _EMAIL_JUNK_EXT):
        return False
    if any(junk in e for junk in _EMAIL_JUNK_SUBSTRINGS):
        return False
    # Overly long local part is usually garbage
    local, _, domain = e.partition("@")
    if len(local) > 64 or len(domain) > 253:
        return False
    return True


def normalize_email(email: str | None) -> str | None:
    """Return lowercased, stripped email or None."""
    if not email:
        return None
    e = email.strip().lower()
    return e if is_valid_email(e) else None


def normalize_phone(phone: str | None, default_region: str | None = None) -> str | None:
    """Normalize a phone number to E.164 using ``phonenumbers``.

    Returns None if the number cannot be parsed or is invalid.
    """
    if not phone:
        return None
    try:
        parsed = phonenumbers.parse(phone, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed):
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def is_valid_website(url: str | None) -> bool:
    """Convenience wrapper around is_http_url."""
    return is_http_url(url)
