"""HTML parsing helpers.

Centralises BeautifulSoup construction so we can gracefully degrade from
``lxml`` to the stdlib ``html.parser`` when lxml is not installed (e.g. on
platforms where it can't be compiled, like Python 3.14 on Windows without
a pre-built wheel).
"""

from __future__ import annotations

from bs4 import BeautifulSoup

try:  # pragma: no cover - environment dependent
    import lxml  # noqa: F401

    _DEFAULT_PARSER = "lxml"
except Exception:  # pragma: no cover
    _DEFAULT_PARSER = "html.parser"


def make_soup(markup: str, parser: str | None = None) -> BeautifulSoup:
    """Return a BeautifulSoup object using the best available parser.

    Prefers ``lxml`` (fast, lenient) and falls back to the stdlib
    ``html.parser`` if lxml isn't installed.
    """
    name = parser or _DEFAULT_PARSER
    try:
        return BeautifulSoup(markup, name)
    except Exception:
        # Last-resort fallback: always works.
        return BeautifulSoup(markup, "html.parser")


def default_parser_name() -> str:
    """Return the parser name that :func:`make_soup` will use by default."""
    return _DEFAULT_PARSER
