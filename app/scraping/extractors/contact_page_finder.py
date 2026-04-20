"""Find candidate contact/about page URLs on a given website."""

from __future__ import annotations

from urllib.parse import urlparse

from app.utils.html_tools import make_soup
from app.utils.url_tools import absolute_url, same_domain

# Path fragments that strongly suggest a contact/about page.
_CONTACT_PATH_HINTS: tuple[str, ...] = (
    "contact-us",
    "contactus",
    "contact",
    "get-in-touch",
    "getintouch",
    "reach-us",
    "reachus",
    "about-us",
    "aboutus",
    "about",
    "team",
    "company",
    "impressum",  # Germany legal page often has contact info
    "imprint",
)

# Anchor text hints (case-insensitive, exact word match).
_CONTACT_TEXT_HINTS: tuple[str, ...] = (
    "contact",
    "contact us",
    "contact-us",
    "get in touch",
    "reach us",
    "about",
    "about us",
    "impressum",
    "imprint",
)


def _score_link(href: str, text: str) -> int:
    """Assign a priority score to a link; higher = more likely contact page.

    Returns 0 for links that don't look like contact/about pages.
    """
    path = urlparse(href).path.lower()
    text_l = (text or "").strip().lower()
    score = 0
    matched = False

    for i, hint in enumerate(_CONTACT_PATH_HINTS):
        if hint in path:
            score += 20 - i  # earlier hints weigh more
            matched = True
            break

    for hint in _CONTACT_TEXT_HINTS:
        if hint == text_l or f" {hint} " in f" {text_l} ":
            score += 10
            matched = True
            break

    # No contact/about signal at all -> not a candidate.
    if not matched:
        return 0

    # Deep paths are less likely the main contact page.
    depth = path.count("/")
    if depth > 3:
        score -= 3

    # Prefer short paths.
    if len(path) < 20:
        score += 2

    return score


def find_contact_pages(html: str, base_url: str, limit: int = 3) -> list[str]:
    """Return up to ``limit`` candidate contact/about URLs on the same domain.

    Results are ordered by relevance score.
    """
    if not html or not base_url:
        return []

    try:
        soup = make_soup(html)
    except Exception:
        return []

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        resolved = absolute_url(base_url, href)
        if not resolved:
            continue
        if not same_domain(resolved, base_url):
            continue
        if resolved in seen:
            continue

        text = a.get_text(" ", strip=True) or ""
        s = _score_link(resolved, text)
        if s <= 0:
            continue
        seen.add(resolved)
        scored.append((s, resolved))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [u for _, u in scored[:limit]]
