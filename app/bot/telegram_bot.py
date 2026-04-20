"""Build and run the Telegram Application."""

from __future__ import annotations

from typing import Awaitable, Callable

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot.handlers import (
    example,
    handle_text,
    help_cmd,
    menu_callback,
    on_error,
    start,
)
from app.bot.wizard import build_wizard_handler
from app.config import settings
from app.logging_config import get_logger
from app.services.lead_service import LeadService

log = get_logger(__name__)


PostInit = Callable[[Application], Awaitable[None]]


def build_application(
    lead_service: LeadService,
    *,
    post_init: PostInit | None = None,
) -> Application:
    """Create and wire up the python-telegram-bot Application.

    Args:
        lead_service: Pre-built lead generation service (stashed into bot_data).
        post_init: Optional async callback invoked once PTB's own event loop is
            running, before polling starts.  Ideal place to run any async
            initialisation (e.g. ``await db.init()``).
    """
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and add your token."
        )

    builder = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
    )
    if post_init is not None:
        builder = builder.post_init(post_init)

    app: Application = builder.build()

    # Stash shared services in bot_data so handlers can reach them without globals.
    app.bot_data["lead_service"] = lead_service

    # ---- Commands ----
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("example", example))

    # ---- Guided wizard (must be registered BEFORE the global text handler so
    # its MessageHandlers win when the user is mid-conversation) ----
    app.add_handler(build_wizard_handler())

    # ---- Menu callbacks (everything except menu:new and wizard:* which the
    # wizard owns) ----
    app.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^menu:(examples|help|main)$",
        )
    )

    # ---- Free-text fallback: any non-command text not consumed by the wizard
    # is treated as a natural-language lead request. ----
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(on_error)
    return app
