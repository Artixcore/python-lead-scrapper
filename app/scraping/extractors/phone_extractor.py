"""Phone number extractor using ``phonenumbers``."""

from __future__ import annotations

import re

import phonenumbers

from app.utils.html_tools import make_soup

_TEL_RE = re.compile(r"tel:([^\"'\s<>]+)", re.IGNORECASE)

# Rough numeric pattern to identify candidates before passing to phonenumbers.
_CAND_RE = re.compile(r"[+(]?\d[\d\s().\-/]{6,}\d")


def _candidates_from_html(html: str) -> list[str]:
    cands: list[str] = []
    # 1) tel: links first
    cands.extend(_TEL_RE.findall(html or ""))

    # 2) text scan
    try:
        text = make_soup(html).get_text(" ", strip=True)
    except Exception:
        text = html or ""

    cands.extend(_CAND_RE.findall(text))
    return cands


def extract_phones(html_or_text: str, default_region: str | None = None) -> list[str]:
    """Extract unique, E.164-formatted phone numbers from HTML or text.

    ``default_region`` should be an ISO-3166-1 alpha-2 code (e.g. 'US', 'GB').
    It is used when the number isn't in international format.
    """
    if not html_or_text:
        return []

    out: list[str] = []
    seen: set[str] = set()

    # Try phonenumbers.PhoneNumberMatcher on plain text first (robust).
    try:
        text_blob = make_soup(html_or_text).get_text(" ", strip=True)
    except Exception:
        text_blob = html_or_text

    for region in _regions_to_try(default_region):
        try:
            for match in phonenumbers.PhoneNumberMatcher(text_blob, region):
                if not phonenumbers.is_valid_number(match.number):
                    continue
                e164 = phonenumbers.format_number(
                    match.number, phonenumbers.PhoneNumberFormat.E164
                )
                if e164 not in seen:
                    seen.add(e164)
                    out.append(e164)
        except Exception:
            continue

    # Also sweep individual candidates to catch tel: links etc.
    for cand in _candidates_from_html(html_or_text):
        for region in _regions_to_try(default_region):
            try:
                parsed = phonenumbers.parse(cand, region)
            except phonenumbers.NumberParseException:
                continue
            if not phonenumbers.is_valid_number(parsed):
                continue
            e164 = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
            if e164 not in seen:
                seen.add(e164)
                out.append(e164)
            break  # stop region loop once parsed

    return out


def _regions_to_try(default_region: str | None) -> list[str | None]:
    """Return regions to try (default first, then None, then common fallbacks)."""
    regions: list[str | None] = []
    if default_region:
        regions.append(default_region.upper())
    regions.append(None)
    for r in ("US", "GB", "FR", "DE", "CA", "AU", "IN"):
        if r not in regions:
            regions.append(r)
    return regions
