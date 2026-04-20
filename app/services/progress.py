"""Progress-reporting primitives.

``Progress`` is the structured value emitted by the lead pipeline during a
job.  It is deliberately transport-agnostic: the pipeline doesn't know (or
care) whether the receiver is the Telegram bot, a log sink, or a CLI.

The Telegram-side renderer lives in :mod:`app.bot.progress_reporter`; the
pure-text bar renderer lives here so it can be re-used and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


# --------------------------------------------------------------------------- #
# Stage weights (total must be 100)
# --------------------------------------------------------------------------- #

#: Percentage ranges per stage, used by the pipeline to compute a monotonic
#: overall percentage.  Tuples are ``(start, end)``.
STAGE_RANGES: dict[str, tuple[int, int]] = {
    "Starting": (0, 1),
    "Discovering": (1, 20),
    "Deduplicating": (20, 25),
    "Enriching": (25, 90),
    "Scoring": (90, 95),
    "Exporting": (95, 100),
    "Done": (100, 100),
}


# --------------------------------------------------------------------------- #
# Progress value
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Progress:
    """A single progress snapshot."""

    percent: int
    stage: str
    detail: str = ""

    def clamp(self) -> "Progress":
        """Return a copy with ``percent`` clamped to 0..100."""
        p = max(0, min(100, int(self.percent)))
        return Progress(percent=p, stage=self.stage, detail=self.detail)


#: Async callback invoked by the pipeline at each progress event.
ProgressCb = Callable[[Progress], Awaitable[None]]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def stage_percent(stage: str, fraction: float = 1.0) -> int:
    """Return an absolute percent for ``stage`` given an in-stage ``fraction``.

    ``fraction`` must be in 0..1 and indicates how far through the current
    stage we are.  Example: ``stage_percent("Enriching", 0.5)`` returns
    roughly 57 (= halfway between 25 and 90).
    """
    start, end = STAGE_RANGES.get(stage, (0, 100))
    frac = max(0.0, min(1.0, float(fraction)))
    return int(round(start + (end - start) * frac))


# --------------------------------------------------------------------------- #
# Bar renderer
# --------------------------------------------------------------------------- #


_BAR_FILLED = "\u2588"  # full block  █
_BAR_EMPTY = "\u2591"   # light shade ░


def render_progress(progress: Progress, *, width: int = 20) -> str:
    """Render a multi-line progress message suitable for Telegram/CLI.

    Example output::

        [██████████░░░░░░░░░░] 50%
        Enriching - 12 / 24 websites

    The first line is always an ASCII-width-safe bar so it renders nicely in
    every chat client; the second line carries the human-readable context.
    """
    p = progress.clamp()
    width = max(4, int(width))
    filled = round(width * p.percent / 100)
    filled = max(0, min(width, filled))
    bar = _BAR_FILLED * filled + _BAR_EMPTY * (width - filled)
    line1 = f"[{bar}] {p.percent}%"
    line2 = p.stage
    if p.detail:
        line2 = f"{line2} - {p.detail}"
    return f"{line1}\n{line2}"
