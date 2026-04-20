"""Application entrypoint.

Run with: ``python -m app.main``
"""

from __future__ import annotations

import asyncio
import sys

from telegram.ext import Application

from app.bot.telegram_bot import build_application
from app.config import settings
from app.db.sqlite import SQLiteDB
from app.logging_config import configure_logging, get_logger
from app.services.lead_service import build_default_lead_service

log = get_logger(__name__)


def main() -> int:
    configure_logging()

    if not settings.telegram_bot_token:
        log.error(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and add your token."
        )
        return 1

    # Construct services synchronously. ``SQLiteDB()`` does no I/O in __init__;
    # only ``.init()`` (create-table) is async, and that is awaited from PTB's
    # own event loop via ``post_init`` below.
    db = SQLiteDB()
    lead_service = build_default_lead_service(db=db)

    async def _post_init(application: Application) -> None:
        await db.init()
        log.info("Bot started. Listening for updates...")

    application = build_application(lead_service, post_init=_post_init)

    # python-telegram-bot 21.x calls ``asyncio.get_event_loop()`` internally
    # which on Python 3.14 raises when no loop is current. Ensure one exists
    # for the main thread (this is a no-op on older Pythons that still
    # auto-create a loop).
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        application.run_polling(drop_pending_updates=False)
    except KeyboardInterrupt:  # pragma: no cover
        log.info("Interrupted; shutting down.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
