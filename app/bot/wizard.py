"""Guided lead-request wizard built on top of PTB's ConversationHandler.

Flow:
    /new  or  tap "New Lead Search"
      -> CHOOSE_TYPE    (pick from grid, or "Custom" to type it)
      -> ENTER_LOC      (user types a city / country)
      -> CHOOSE_COUNT   (10 / 20 / 50 / 100)
      -> CHOOSE_REQS    (multi-select: website / email / phone / social)
      -> CONFIRM        (review and launch)

Cancel is always available via a button or the /cancel command.
"""

from __future__ import annotations

import warnings
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import messages
from app.bot.handlers import run_lead_job
from app.bot.keyboards import (
    business_type_kb,
    confirm_kb,
    count_kb,
    main_menu_kb,
    requirements_kb,
)
from app.logging_config import get_logger
from app.parsing.request_parser import ParseError, parse_request

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# States
# --------------------------------------------------------------------------- #

CHOOSE_TYPE, ENTER_LOC, CHOOSE_COUNT, CHOOSE_REQS, CONFIRM = range(5)


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


async def start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point. Reachable via /new or the 'New Lead Search' button."""
    context.user_data.clear()
    context.user_data["wizard"] = _fresh_state()

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(
            messages.WIZ_CHOOSE_TYPE,
            reply_markup=business_type_kb(),
        )
    elif update.message:
        await update.message.reply_text(
            messages.WIZ_CHOOSE_TYPE,
            reply_markup=business_type_kb(),
        )
    return CHOOSE_TYPE


# --------------------------------------------------------------------------- #
# Step: choose type
# --------------------------------------------------------------------------- #


async def on_type_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if not q or not q.data:
        return CHOOSE_TYPE
    await q.answer()

    _, value = q.data.split(":", 1)

    if value == "__custom__":
        await q.edit_message_text(
            messages.WIZ_CUSTOM_TYPE,
            parse_mode=ParseMode.MARKDOWN,
        )
        return CHOOSE_TYPE

    context.user_data["wizard"]["keyword"] = value
    await q.edit_message_text(
        messages.WIZ_ENTER_LOCATION.format(keyword=value),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ENTER_LOC


async def on_type_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a custom business type."""
    if not update.message or not update.message.text:
        return CHOOSE_TYPE
    keyword = update.message.text.strip().lower()
    if not keyword:
        await update.message.reply_text("Please type a business type.")
        return CHOOSE_TYPE

    context.user_data["wizard"]["keyword"] = keyword
    await update.message.reply_text(
        messages.WIZ_ENTER_LOCATION.format(keyword=keyword),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ENTER_LOC


# --------------------------------------------------------------------------- #
# Step: enter location
# --------------------------------------------------------------------------- #


async def on_location_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return ENTER_LOC
    loc = update.message.text.strip()
    if not loc:
        await update.message.reply_text(messages.WIZ_INVALID_LOCATION)
        return ENTER_LOC

    context.user_data["wizard"]["location"] = loc
    await update.message.reply_text(
        messages.WIZ_CHOOSE_COUNT,
        reply_markup=count_kb(),
    )
    return CHOOSE_COUNT


# --------------------------------------------------------------------------- #
# Step: choose count
# --------------------------------------------------------------------------- #


async def on_count_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if not q or not q.data:
        return CHOOSE_COUNT
    await q.answer()

    _, raw = q.data.split(":", 1)
    try:
        n = int(raw)
    except ValueError:
        n = 20
    context.user_data["wizard"]["max_leads"] = n

    await q.edit_message_text(
        messages.WIZ_CHOOSE_REQS,
        reply_markup=requirements_kb(context.user_data["wizard"]["requirements"]),
        parse_mode=ParseMode.MARKDOWN,
    )
    return CHOOSE_REQS


# --------------------------------------------------------------------------- #
# Step: toggle requirements
# --------------------------------------------------------------------------- #


async def on_req_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if not q or not q.data:
        return CHOOSE_REQS
    await q.answer()

    _, key = q.data.split(":", 1)
    wiz = context.user_data["wizard"]

    if key == "done":
        await q.edit_message_text(
            _build_confirm_text(wiz),
            reply_markup=confirm_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return CONFIRM

    reqs: dict[str, bool] = wiz["requirements"]
    reqs[key] = not reqs.get(key, False)
    try:
        await q.edit_message_reply_markup(reply_markup=requirements_kb(reqs))
    except Exception:  # pragma: no cover - happens if markup didn't change
        pass
    return CHOOSE_REQS


# --------------------------------------------------------------------------- #
# Step: confirm
# --------------------------------------------------------------------------- #


async def on_confirm_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if not q or not q.data:
        return CONFIRM
    await q.answer()

    wiz = context.user_data["wizard"]
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None

    # Turn the wizard state into a LeadRequest by running it through the same
    # deterministic parser used for free-text queries. This preserves all the
    # inference logic (country-from-city, industry lookup, etc.).
    try:
        query = _build_query_string(wiz)
        request = parse_request(query)
    except ParseError as e:
        primary = "; ".join(i.message for i in e.issues)
        await q.edit_message_text(
            f"Couldn't build a valid request: {primary}\n\nSend /new to start over.",
            reply_markup=main_menu_kb(),
        )
        return ConversationHandler.END

    await q.edit_message_text(
        messages.format_acknowledgement(request),
        parse_mode=ParseMode.MARKDOWN,
    )

    if chat_id is not None:
        await run_lead_job(context, chat_id, user_id, request)

    context.user_data.clear()
    return ConversationHandler.END


# --------------------------------------------------------------------------- #
# Cancel (shared)
# --------------------------------------------------------------------------- #


async def on_cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        try:
            await q.edit_message_text(
                messages.WIZ_CANCELLED,
                reply_markup=main_menu_kb(),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # pragma: no cover
            pass
    context.user_data.clear()
    return ConversationHandler.END


async def on_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text(
            messages.WIZ_CANCELLED,
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
    context.user_data.clear()
    return ConversationHandler.END


# --------------------------------------------------------------------------- #
# ConversationHandler factory
# --------------------------------------------------------------------------- #


def build_wizard_handler() -> ConversationHandler:
    """Return the wizard ConversationHandler wired with all its states.

    The ``per_message=False`` default is intentional: we mix CallbackQueryHandler
    (buttons) and MessageHandler (text) in the same states, and tracking per
    user/chat (not per message) is what we want. PTB emits an informational
    warning about this combination that we suppress for clean startup logs.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*per_message=False.*CallbackQueryHandler.*",
        )
        return ConversationHandler(
            entry_points=[
                CommandHandler("new", start_wizard),
                CallbackQueryHandler(start_wizard, pattern=r"^menu:new$"),
            ],
            states={
                CHOOSE_TYPE: [
                    CallbackQueryHandler(on_type_button, pattern=r"^type:"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, on_type_text),
                ],
                ENTER_LOC: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, on_location_text),
                ],
                CHOOSE_COUNT: [
                    CallbackQueryHandler(on_count_button, pattern=r"^count:"),
                ],
                CHOOSE_REQS: [
                    CallbackQueryHandler(on_req_button, pattern=r"^req:"),
                ],
                CONFIRM: [
                    CallbackQueryHandler(on_confirm_button, pattern=r"^confirm:go$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", on_cancel_command),
                CallbackQueryHandler(on_cancel_button, pattern=r"^wizard:cancel$"),
            ],
            # Allow /new to restart mid-conversation.
            allow_reentry=True,
            # Clean up abandoned sessions after 10 minutes of inactivity.
            conversation_timeout=600,
            name="lead_wizard",
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fresh_state() -> dict[str, Any]:
    from app.config import settings

    return {
        "keyword": None,
        "location": None,
        "max_leads": settings.default_max_leads,
        "requirements": {
            "website_required": False,
            "email_required": False,
            "phone_required": False,
            "social_required": False,
        },
    }


def _build_query_string(wiz: dict[str, Any]) -> str:
    """Assemble a natural-language query from collected wizard state."""
    parts = [f"Find {wiz['max_leads']} {wiz['keyword']} in {wiz['location']}"]

    reqs_kw = []
    if wiz["requirements"].get("website_required"):
        reqs_kw.append("website")
    if wiz["requirements"].get("email_required"):
        reqs_kw.append("email")
    if wiz["requirements"].get("phone_required"):
        reqs_kw.append("phone")
    if wiz["requirements"].get("social_required"):
        reqs_kw.append("social")

    if reqs_kw:
        parts.append("with " + " and ".join(reqs_kw))

    return " ".join(parts)


def _build_confirm_text(wiz: dict[str, Any]) -> str:
    reqs_selected = [
        label
        for key, label in [
            ("website_required", "website"),
            ("email_required", "email"),
            ("phone_required", "phone"),
            ("social_required", "social"),
        ]
        if wiz["requirements"].get(key)
    ]
    reqs_str = ", ".join(reqs_selected) if reqs_selected else "(none)"

    return messages.WIZ_CONFIRM.format(
        count=wiz["max_leads"],
        keyword=wiz["keyword"],
        location=wiz["location"],
        reqs=reqs_str,
    )
