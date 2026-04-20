"""Telegram-side progress reporter.

Owns a single chat message which is edited in-place as the pipeline emits
:class:`Progress` snapshots.  Edits are throttled so we don't hit Telegram's
rate limits when a job produces many rapid updates (e.g. per-lead enrichment
progress on a 100-lead job).
"""

from __future__ import annotations

import asyncio
import time

from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from app.logging_config import get_logger
from app.services.progress import Progress, render_progress

log = get_logger(__name__)


# Minimum time between edits (Telegram recommends <= 1 edit/sec/same-message).
_MIN_EDIT_INTERVAL = 1.0
# Also throttle by percent delta so rapid small bumps don't each cause an edit.
_MIN_PERCENT_DELTA = 3


class ProgressReporter:
    """Manages a single Telegram message that represents a job's progress.

    Usage::

        reporter = ProgressReporter(context, chat_id)
        await reporter(Progress(10, "Discovering"))
        ...
        await reporter.finish("All done.")
    """

    def __init__(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        *,
        min_edit_interval: float = _MIN_EDIT_INTERVAL,
        min_percent_delta: int = _MIN_PERCENT_DELTA,
    ) -> None:
        self._context = context
        self._chat_id = chat_id
        self._message_id: int | None = None
        self._last_edit_ts = 0.0
        self._last_percent = -1
        self._last_stage = ""
        self._last_text = ""
        self._min_interval = float(min_edit_interval)
        self._min_delta = int(min_percent_delta)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def __call__(self, progress: Progress) -> None:
        """Update the progress message (creates it on first call)."""
        await self.update(progress)

    async def update(self, progress: Progress) -> None:
        """Throttled in-place edit of the progress message."""
        async with self._lock:
            p = progress.clamp()
            now = time.monotonic()

            stage_changed = p.stage != self._last_stage
            percent_delta_ok = (p.percent - self._last_percent) >= self._min_delta
            time_ok = (now - self._last_edit_ts) >= self._min_interval
            is_terminal = p.percent >= 100

            # First edit always flushes; otherwise must pass a throttle check.
            is_first = self._message_id is None
            if not (is_first or stage_changed or is_terminal or (percent_delta_ok and time_ok)):
                return

            text = render_progress(p)
            if text == self._last_text and not is_terminal:
                return

            try:
                if self._message_id is None:
                    msg = await self._context.bot.send_message(
                        chat_id=self._chat_id,
                        text=text,
                    )
                    self._message_id = msg.message_id
                else:
                    await self._context.bot.edit_message_text(
                        chat_id=self._chat_id,
                        message_id=self._message_id,
                        text=text,
                    )
            except RetryAfter as e:
                # Back off silently; Telegram asked us to wait.
                log.debug("Telegram RetryAfter %.1fs; skipping this edit.", float(e.retry_after))
                return
            except BadRequest as e:
                # Most common: "Message is not modified" -- safe to ignore.
                if "not modified" in str(e).lower():
                    pass
                else:
                    log.debug("BadRequest editing progress: %s", e)
            except TelegramError as e:  # pragma: no cover
                log.debug("Telegram error updating progress: %s", e)
                return

            self._last_edit_ts = now
            self._last_percent = p.percent
            self._last_stage = p.stage
            self._last_text = text

    async def finish(self, text: str | None = None) -> None:
        """Replace the progress bar with a short completion message."""
        async with self._lock:
            if self._message_id is None:
                # No message was ever sent; nothing to do.
                return
            final_text = text or render_progress(Progress(100, "Done"))
            try:
                await self._context.bot.edit_message_text(
                    chat_id=self._chat_id,
                    message_id=self._message_id,
                    text=final_text,
                )
            except BadRequest as e:
                if "not modified" not in str(e).lower():
                    log.debug("BadRequest finishing progress: %s", e)
            except TelegramError as e:  # pragma: no cover
                log.debug("Telegram error finishing progress: %s", e)
