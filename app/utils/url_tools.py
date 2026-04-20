"""URL normalization and parsing helpers."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse

import tldextract


def is_http_url(url: str | None) -> bool:
    """True if ``url`` is a syntactically valid http(s) URL."""
    if not url:
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme in {"http", "https"} and bool(p.netloc)


def normalize_url(url: str | None) -> str | None:
    """Normalize a URL: add scheme if missing, lowercase host, drop fragment."""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # Add scheme if missing
    if "://" not in url:
        url = "http://" + url.lstrip("/")

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc.lower()
    if not netloc:
        return None

    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    if path == "":
        path = "/"

    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def get_domain(url: str | None) -> str | None:
    """Return the registered domain (e.g. example.com) for a URL."""
    if not url:
        return None
    try:
        ext = tldextract.extract(url)
    except Exception:
        return None
    if not ext.domain:
        return None
    if ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return ext.domain.lower()


def same_domain(a: str | None, b: str | None) -> bool:
    da, db = get_domain(a), get_domain(b)
    return bool(da and db and da == db)


def absolute_url(base: str, href: str) -> str | None:
    """Resolve ``href`` against ``base`` and normalize."""
    if not href:
        return None
    try:
        joined = urljoin(base, href)
    except ValueError:
        return None
    return normalize_url(joined)


def root_url(url: str | None) -> str | None:
    """Return the root of a URL, e.g. https://example.com/."""
    norm = normalize_url(url)
    if not norm:
        return None
    p = urlparse(norm)
    return f"{p.scheme}://{p.netloc}/"
