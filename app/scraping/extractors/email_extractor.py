"""Email extractor with light junk filtering."""

from __future__ import annotations

import re
from urllib.parse import unquote

from app.utils.html_tools import make_soup
from app.utils.validators import is_valid_email, normalize_email

# Slightly loose regex so we can catch common obfuscations in HTML/text.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)

# Common "@" obfuscations we try to un-mangle before regex matching.
_OBFUSCATIONS = [
    (re.compile(r"\s*\(\s*at\s*\)\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s*\[\s*at\s*\]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s+at\s+", re.IGNORECASE), "@"),
    (re.compile(r"\s*\(\s*dot\s*\)\s*", re.IGNORECASE), "."),
    (re.compile(r"\s*\[\s*dot\s*\]\s*", re.IGNORECASE), "."),
    (re.compile(r"\s+dot\s+", re.IGNORECASE), "."),
]


def _deobfuscate(text: str) -> str:
    """Undo simple "name (at) domain dot com" style obfuscations."""
    for pattern, repl in _OBFUSCATIONS:
        text = pattern.sub(repl, text)
    return text


def extract_emails(html_or_text: str) -> list[str]:
    """Extract unique, cleaned, likely-real emails from HTML or plain text.

    Returns an ordered list (insertion order, deduplicated).
    """
    if not html_or_text:
        return []

    candidates: list[str] = []

    # 1) Parse HTML; look at mailto: links first (highest confidence).
    try:
        soup = make_soup(html_or_text)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                email = unquote(href[7:]).split("?", 1)[0]
                if email:
                    candidates.append(email)

        text_blob = soup.get_text(" ", strip=True)
    except Exception:
        text_blob = html_or_text

    # 2) Regex scan across the (deobfuscated) text.
    text_blob = _deobfuscate(text_blob)
    for m in _EMAIL_RE.findall(text_blob):
        candidates.append(m)

    # 3) Also scan the raw input (to catch emails in scripts / attrs).
    raw_deob = _deobfuscate(html_or_text)
    for m in _EMAIL_RE.findall(raw_deob):
        candidates.append(m)

    # Dedup + validate
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        email = normalize_email(c)
        if not email or email in seen:
            continue
        if not is_valid_email(email):
            continue
        seen.add(email)
        result.append(email)
    return result
