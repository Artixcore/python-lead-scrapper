"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any, Callable, Iterable


class FakeHTTPClient:
    """Lightweight stand-in for :class:`app.scraping.base.HTTPClient`.

    Tests can either provide a ``handler(url, params, headers)`` callable that
    returns a response payload, or append canned responses to ``json_queue``
    / ``text_queue`` which are drained FIFO.

    The fake records every request in ``calls`` so tests can assert on
    params, headers, ordering, etc.
    """

    def __init__(
        self,
        *,
        handler: Callable[[str, dict | None, dict | None], Any] | None = None,
        json_responses: Iterable[Any] | None = None,
        text_responses: Iterable[str | None] | None = None,
    ) -> None:
        self._handler = handler
        self._json_queue: list[Any] = list(json_responses or [])
        self._text_queue: list[str | None] = list(text_responses or [])
        self.calls: list[dict[str, Any]] = []

    # ---- Queue helpers ------------------------------------------------- #

    def push_json(self, payload: Any) -> None:
        self._json_queue.append(payload)

    def push_text(self, payload: str | None) -> None:
        self._text_queue.append(payload)

    # ---- HTTPClient surface ------------------------------------------- #

    async def get_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        self.calls.append(
            {"kind": "json", "url": url, "params": params, "headers": headers}
        )
        if self._handler is not None:
            return self._handler(url, params, headers)
        if not self._json_queue:
            return None
        return self._json_queue.pop(0)

    async def get_text(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> str | None:
        self.calls.append(
            {"kind": "text", "url": url, "params": params, "headers": headers}
        )
        if self._handler is not None:
            return self._handler(url, params, headers)
        if not self._text_queue:
            return None
        return self._text_queue.pop(0)
