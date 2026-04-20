"""Retry helpers built on top of ``tenacity``."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")

_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
)


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 8.0,
) -> T:
    """Run ``func()`` with exponential backoff on transient HTTP errors.

    Raises the final underlying exception (not a tenacity wrapper).
    """
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=min_wait, max=max_wait),
            retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
            reraise=True,
        ):
            with attempt:
                return await func()
    except RetryError as e:  # pragma: no cover - reraise=True makes this unreachable
        raise e.last_attempt.exception() or RuntimeError("retry failed")

    raise RuntimeError("unreachable")  # pragma: no cover
