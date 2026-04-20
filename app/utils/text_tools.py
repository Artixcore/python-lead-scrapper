"""Small text-cleaning helpers."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def clean_whitespace(s: str | None) -> str | None:
    """Collapse whitespace and strip, returning None for empty results."""
    if s is None:
        return None
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s or None


def normalize_unicode(s: str | None) -> str | None:
    """Unicode normalize (NFKC) and strip."""
    if s is None:
        return None
    return unicodedata.normalize("NFKC", s).strip() or None


def truncate(s: str | None, length: int = 240) -> str | None:
    """Truncate a string with an ellipsis if it exceeds ``length``."""
    if s is None:
        return None
    s = s.strip()
    if len(s) <= length:
        return s or None
    return s[: length - 1].rstrip() + "\u2026"


def safe_lower(s: str | None) -> str | None:
    return s.lower() if isinstance(s, str) and s else None


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def slugify_name(s: str | None) -> str | None:
    """Lowercase, strip punctuation + whitespace -- useful for dedup keys."""
    if not s:
        return None
    s = normalize_unicode(s) or ""
    s = _PUNCT_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip().lower()
    return s or None
