"""Social media link extractor (LinkedIn, Facebook, Instagram, X/Twitter)."""

from __future__ import annotations

from urllib.parse import urlparse

from app.utils.html_tools import make_soup
from app.utils.url_tools import absolute_url, normalize_url

# domain -> model field
_SOCIAL_DOMAINS: dict[str, str] = {
    "linkedin.com": "linkedin_url",
    "www.linkedin.com": "linkedin_url",
    "facebook.com": "facebook_url",
    "www.facebook.com": "facebook_url",
    "fb.com": "facebook_url",
    "m.facebook.com": "facebook_url",
    "instagram.com": "instagram_url",
    "www.instagram.com": "instagram_url",
    "twitter.com": "twitter_url",
    "www.twitter.com": "twitter_url",
    "x.com": "twitter_url",
    "www.x.com": "twitter_url",
}

# Paths we skip (e.g. a "share on Facebook" link).
_SKIP_PATH_SUBSTRINGS = (
    "/sharer",
    "/share",
    "/intent/",
    "/share.php",
    "/dialog/share",
)


def extract_social_links(html: str, base_url: str | None = None) -> dict[str, str]:
    """Return a dict with keys: linkedin_url, facebook_url, instagram_url, twitter_url.

    Only the first link found per platform is kept.
    """
    if not html:
        return {}

    found: dict[str, str] = {}

    try:
        soup = make_soup(html)
    except Exception:
        return {}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        resolved = absolute_url(base_url, href) if base_url else normalize_url(href)
        if not resolved:
            continue

        host = urlparse(resolved).netloc.lower()
        field = _SOCIAL_DOMAINS.get(host)
        if not field:
            continue

        path_lower = urlparse(resolved).path.lower()
        if any(skip in path_lower for skip in _SKIP_PATH_SUBSTRINGS):
            continue

        # Skip bare domain (e.g. https://facebook.com/ with no page).
        if path_lower in ("", "/"):
            continue

        if field not in found:
            found[field] = resolved

    return found
