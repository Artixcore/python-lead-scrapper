"""Parse free-text user messages into ``LeadRequest`` objects.

The parser is deterministic / rule-based by default.  An LLM-based parser can
later be plugged in by subclassing :class:`RequestParser` and overriding
``parse``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from pydantic import ValidationError

from app.config import settings
from app.models.lead_request import LeadRequest
from app.parsing.normalizers import (
    BUSINESS_TYPE_MAP,
    COUNTRY_ALIASES,
    business_type_for,
    industry_for,
    infer_country_from_city,
    infer_state_from_city,
    normalize_country,
)


# --------------------------------------------------------------------------- #
# Token helpers
# --------------------------------------------------------------------------- #

_NUMBER_RE = re.compile(r"\b(\d{1,4})\b")

_REQUIREMENT_TOKENS = {
    "email": "email_required",
    "emails": "email_required",
    "e-mail": "email_required",
    "website": "website_required",
    "websites": "website_required",
    "site": "website_required",
    "phone": "phone_required",
    "phones": "phone_required",
    "phone number": "phone_required",
    "phone numbers": "phone_required",
    "telephone": "phone_required",
    "tel": "phone_required",
    "social": "social_required",
    "socials": "social_required",
    "social media": "social_required",
    "linkedin": "social_required",
    "facebook": "social_required",
    "instagram": "social_required",
    "twitter": "social_required",
}

# Phrases that introduce a requirement list.
_WITH_RE = re.compile(
    r"\bwith\s+(?P<body>[^.]+?)(?:\s+and\s+|$|,)", re.IGNORECASE
)

# Phrases that introduce a location.
#   ... in Dallas
#   ... in Dallas, Texas
#   ... in Paris, France
#   ... in New York, USA
_LOCATION_RE = re.compile(
    r"\b(?:in|from|near|around|at|located\s+in)\s+"
    r"(?P<loc>[A-Za-z][\w .\-]*(?:,\s*[A-Za-z][\w .\-]*){0,2})",
    re.IGNORECASE,
)

# Verbs/prefixes we strip from the front of a request.
_LEAD_VERB_RE = re.compile(
    r"^\s*(?:"
    r"please\s+|"
    r"can\s+you\s+|"
    r"could\s+you\s+|"
    r"i\s+(?:want|need|would\s+like)\s+(?:to\s+)?|"
    r"get\s+me\s+|"
    r"give\s+me\s+|"
    r"show\s+me\s+|"
    r"scrape(?:\s+me)?\s+|"
    r"find\s+me\s+|"
    r"find\s+|"
    r"need\s+|"
    r"get\s+|"
    r"show\s+|"
    r"looking\s+for\s+|"
    r"search\s+(?:for\s+)?|"
    r"lookup\s+"
    r")",
    re.IGNORECASE,
)

# Filler tail words that are not part of the keyword.
_FILLER_WORDS = {
    "leads",
    "lead",
    "contacts",
    "contact",
    "businesses",
    "business",
    "companies",
    "company",
    "firms",
    "firm",
    "list",
    "lists",
    "results",
}


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass
class ParseIssue:
    """Describes why parsing failed or produced a clarification request."""

    field: str  # e.g. 'location', 'keyword'
    message: str  # user-friendly question / error


class ParseError(Exception):
    """Raised when parsing cannot produce a valid request (needs clarification)."""

    def __init__(self, issues: list[ParseIssue]):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))


# --------------------------------------------------------------------------- #
# The parser
# --------------------------------------------------------------------------- #


class RequestParser:
    """Deterministic, rule-based natural language parser."""

    def parse(self, text: str) -> LeadRequest:
        """Parse ``text`` into a :class:`LeadRequest`.

        Raises :class:`ParseError` when key fields (keyword / location) are
        missing so the caller can ask a follow-up.
        """
        if not text or not text.strip():
            raise ParseError([ParseIssue("keyword", "Please send a lead request.")])

        raw = text.strip()
        cleaned = _LEAD_VERB_RE.sub("", raw).strip()

        max_leads = self._extract_max_leads(cleaned)
        # Remove the number from the working text so it doesn't contaminate
        # keyword extraction.
        working = _NUMBER_RE.sub(" ", cleaned, count=1).strip()

        requirements = self._extract_requirements(working)
        # Strip the "with ..." tail so we don't confuse the keyword extractor.
        working_no_with = re.sub(r"\bwith\b[^.]*", " ", working, flags=re.IGNORECASE)

        location_match = _LOCATION_RE.search(working_no_with)
        city, state, country = None, None, None
        if location_match:
            loc_raw = location_match.group("loc").strip().strip(",. ")
            city, state, country = self._split_location(loc_raw)
            # Remove location phrase from the working text.
            working_no_loc = working_no_with[: location_match.start()]
        else:
            working_no_loc = working_no_with

        keyword = self._extract_keyword(working_no_loc)

        # ---- Fallback inferences ----
        if city and not country:
            country = infer_country_from_city(city)
        if city and not state and (country is None or country == "USA"):
            state = infer_state_from_city(city)
        country = normalize_country(country) if country else None

        # ---- Issues / clarifications ----
        issues: list[ParseIssue] = []
        if not keyword:
            issues.append(
                ParseIssue(
                    "keyword",
                    "What type of business leads do you need? "
                    "(e.g. dentists, restaurants, marketing agencies)",
                )
            )
        if not any([city, state, country]):
            issues.append(
                ParseIssue(
                    "location",
                    "Which city or country should I search in?",
                )
            )
        if issues:
            raise ParseError(issues)

        # ---- Apply limits from settings ----
        if max_leads is None:
            max_leads = settings.default_max_leads
        max_leads = max(1, min(max_leads, settings.max_leads_limit))

        # ---- Build the LeadRequest ----
        biz_type = business_type_for(keyword)  # type: ignore[arg-type]
        industry = industry_for(keyword)  # type: ignore[arg-type]

        try:
            return LeadRequest(
                keyword=keyword,  # type: ignore[arg-type]
                business_type=biz_type,
                industry=industry,
                city=city,
                state_or_region=state,
                country=country,
                max_leads=max_leads,
                **requirements,
                notes="",
            )
        except ValidationError as e:  # pragma: no cover - defensive
            raise ParseError(
                [ParseIssue("validation", f"Couldn't build request: {e.errors()}")]
            )

    # ---------------------------------------------------------------- #
    # Individual extractors
    # ---------------------------------------------------------------- #

    def _extract_max_leads(self, text: str) -> int | None:
        m = _NUMBER_RE.search(text)
        if not m:
            return None
        try:
            n = int(m.group(1))
        except ValueError:
            return None
        if n <= 0:
            return None
        return n

    def _extract_requirements(self, text: str) -> dict[str, bool]:
        out = {
            "website_required": False,
            "email_required": False,
            "phone_required": False,
            "social_required": False,
        }

        lower = text.lower()
        for token, field in _REQUIREMENT_TOKENS.items():
            if re.search(rf"\b{re.escape(token)}\b", lower):
                out[field] = True

        return out

    def _split_location(self, loc: str) -> tuple[str | None, str | None, str | None]:
        """Split a captured location string into (city, state_or_region, country)."""
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        city = state = country = None

        if len(parts) == 1:
            single = parts[0]
            # Is it a country alias or known country name?
            if single.lower() in COUNTRY_ALIASES:
                country = COUNTRY_ALIASES[single.lower()]
            else:
                city = single
        elif len(parts) == 2:
            city, tail = parts
            tail_norm = COUNTRY_ALIASES.get(tail.lower())
            if tail_norm:
                country = tail_norm
            else:
                # treat tail as state/region
                state = tail
        else:
            city, state, tail = parts[0], parts[1], parts[2]
            country = COUNTRY_ALIASES.get(tail.lower(), tail)

        # clean-up
        city = _clean_token(city)
        state = _clean_token(state)
        country = _clean_token(country)
        return city, state, country

    def _extract_keyword(self, text: str) -> str | None:
        """Pick the keyword/business type out of the remaining text."""
        if not text:
            return None

        # First, try known multi-word business types (longest first).
        lower = text.lower()
        candidates = sorted(BUSINESS_TYPE_MAP.keys(), key=len, reverse=True)
        for phrase in candidates:
            if re.search(rf"\b{re.escape(phrase)}\b", lower):
                return phrase

        # Fallback: strip fillers + punctuation and take leftover words.
        words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text)
        words = [w for w in words if w.lower() not in _FILLER_WORDS]

        # Drop stop-words-like prepositions that might have leaked in.
        stop = {"in", "from", "near", "at", "the", "a", "an", "of", "with", "and", "or"}
        words = [w for w in words if w.lower() not in stop]

        if not words:
            return None

        # Keep at most the first 3 meaningful words.
        keyword = " ".join(words[:3]).strip()
        return keyword.lower() or None


# --------------------------------------------------------------------------- #
# Module-level convenience
# --------------------------------------------------------------------------- #


_parser_singleton: RequestParser | None = None


def parse_request(text: str) -> LeadRequest:
    """Parse using the default parser singleton."""
    global _parser_singleton
    if _parser_singleton is None:
        _parser_singleton = RequestParser()
    return _parser_singleton.parse(text)


# --------------------------------------------------------------------------- #
# private helpers
# --------------------------------------------------------------------------- #


def _clean_token(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().strip(",.;: ")
    return s or None
