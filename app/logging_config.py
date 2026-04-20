"""Central logging configuration."""

from __future__ import annotations

import logging
import sys
from logging import Logger

from app.config import settings


_CONFIGURED = False


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger.

    Safe to call multiple times; only configures once.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = (level or settings.log_level).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(numeric_level)
    root.addHandler(handler)

    # Quiet noisy libraries a bit
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("telegram.ext").setLevel(logging.INFO)

    _CONFIGURED = True


def get_logger(name: str) -> Logger:
    """Return a module logger (and ensure logging is configured)."""
    configure_logging()
    return logging.getLogger(name)
