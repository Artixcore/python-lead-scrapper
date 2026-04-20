"""Top-level Telegram handlers (commands, free-text, menu callbacks).

The guided wizard lives in :mod:`app.bot.wizard` and is wired in
:mod:`app.bot.telegram_bot`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from app.bot import messages
from app.bot.keyboards import after_job_kb, main_menu_kb
from app.logging_config import get_logger
from app.models.lead_request import LeadRequest
from app.parsing.request_parser import ParseError, parse_request
from app.services.lead_service import LeadService

log = get_logger(__name__)


# Global cap on concurrent jobs across all users.
_JOB_SEMAPHORE = asyncio.Semaphore(4)
# Per-user concurrent job tracker (user_id -> count).
_active_jobs: dict[int, int] = {}
_MAX_PER_USER = 1


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            messages.WELCOME,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            messages.HELP,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )


async def example(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            messages.EXAMPLES,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )


# --------------------------------------------------------------------------- #
# Free-text message handler (kept for power users)
# --------------------------------------------------------------------------- #


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat any non-command text message as a lead request."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None

    if chat_id is None:
        return

    # Per-user rate guard
    if user_id is not None and _active_jobs.get(user_id, 0) >= _MAX_PER_USER:
        await update.message.reply_text(
            "You already have a job running. Please wait for it to finish."
        )
        return

    try:
        request: LeadRequest = parse_request(text)
    except ParseError as e:
        await _reply_clarification(update, e)
        return

    await _kick_off_job(context, chat_id, user_id, request)


# --------------------------------------------------------------------------- #
# Menu callback handler (Main Menu / Examples / Help / Main buttons)
# --------------------------------------------------------------------------- #


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on the non-wizard buttons: menu:examples, menu:help, menu:main.

    The ``menu:new`` button is handled by the wizard's ConversationHandler
    (as an entry point), so it never reaches this handler.
    """
    q = update.callback_query
    if not q or not q.data:
        return

    await q.answer()
    data = q.data

    if data == "menu:examples":
        await q.edit_message_text(
            messages.EXAMPLES,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )
    elif data == "menu:help":
        await q.edit_message_text(
            messages.HELP,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )
    elif data == "menu:main":
        await q.edit_message_text(
            messages.WELCOME,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )


# --------------------------------------------------------------------------- #
# Shared job runner (callable from text handler OR wizard)
# --------------------------------------------------------------------------- #


async def run_lead_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int | None,
    request: LeadRequest,
) -> None:
    """Execute the lead pipeline and post the summary + CSV back to chat.

    Designed to be called from both the free-text handler and the wizard's
    final confirm step -- it never touches ``update.message`` directly.
    """
    service: LeadService = context.application.bot_data["lead_service"]

    # Per-user guard
    if user_id is not None and _active_jobs.get(user_id, 0) >= _MAX_PER_USER:
        await context.bot.send_message(
            chat_id=chat_id,
            text="You already have a job running. Please wait for it to finish.",
        )
        return

    if user_id is not None:
        _active_jobs[user_id] = _active_jobs.get(user_id, 0) + 1

    try:
        async with _JOB_SEMAPHORE:
            await _execute_job(context, chat_id, user_id, request, service)
    finally:
        if user_id is not None:
            _active_jobs[user_id] = max(0, _active_jobs.get(user_id, 1) - 1)


async def _kick_off_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int | None,
    request: LeadRequest,
) -> None:
    """Wrapper used by ``handle_text`` for consistent accounting with wizard."""
    if user_id is not None:
        _active_jobs[user_id] = _active_jobs.get(user_id, 0) + 1
    try:
        async with _JOB_SEMAPHORE:
            service: LeadService = context.application.bot_data["lead_service"]
            await _execute_job(context, chat_id, user_id, request, service)
    finally:
        if user_id is not None:
            _active_jobs[user_id] = max(0, _active_jobs.get(user_id, 1) - 1)


# --------------------------------------------------------------------------- #
# Core job flow
# --------------------------------------------------------------------------- #


async def _execute_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int | None,
    request: LeadRequest,
    service: LeadService,
) -> None:
    await _safe_send(
        context,
        chat_id,
        messages.format_acknowledgement(request),
        parse_mode=ParseMode.MARKDOWN,
    )

    async def progress(msg: str) -> None:
        try:
            await context.bot.send_chat_action(
                chat_id=chat_id, action=ChatAction.TYPING
            )
            if any(
                msg.startswith(pref)
                for pref in ("Searching", "Deduplicating", "Enriching", "Scoring")
            ):
                await context.bot.send_message(
                    chat_id=chat_id, text=messages.format_progress(msg)
                )
        except Exception:  # pragma: no cover
            log.debug("Progress update failed.")

    try:
        result, csv_path = await service.run(
            request, user_id=user_id, progress=progress
        )
    except Exception as e:
        log.exception("Pipeline failed: %s", e)
        await _safe_send(
            context,
            chat_id,
            "Sorry, something went wrong while running your request. Please try again.",
        )
        return

    # Summary
    await _safe_send(
        context,
        chat_id,
        messages.format_summary(result),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Contextual notes
    if result.total_cleaned == 0:
        await _safe_send(context, chat_id, messages.LOW_RESULT_WARNING)
    elif result.total_with_email == 0 and request.email_required:
        await _safe_send(context, chat_id, messages.FEW_EMAILS_NOTE)

    # CSV
    await _send_csv(context, chat_id, csv_path)

    # Follow-up buttons
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="What next?",
            reply_markup=after_job_kb(),
        )
    except Exception:  # pragma: no cover
        log.debug("Could not send after-job keyboard.")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Send a message; fall back to plain text if Markdown parsing fails."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    except Exception as e:
        if parse_mode:
            log.warning("Markdown send failed (%s); sending as plain text.", e)
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=reply_markup
                )
                return
            except Exception as e2:  # pragma: no cover
                log.warning("Plain-text send also failed: %s", e2)
        else:  # pragma: no cover
            log.warning("send_message failed: %s", e)


async def _send_csv(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    csv_path: Path,
) -> None:
    try:
        with csv_path.open("rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=csv_path.name,
                caption="Full results (CSV)",
            )
    except Exception as e:
        log.warning("Could not send CSV %s: %s", csv_path, e)
        await _safe_send(
            context,
            chat_id,
            (
                "I generated the CSV but couldn't attach it. "
                f"You can find it on the server at `{csv_path}`."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )


async def _reply_clarification(update: Update, err: ParseError) -> None:
    assert update.message is not None
    primary = err.issues[0].message
    extra = "\n".join(f"- {i.message}" for i in err.issues[1:])
    msg = primary if not extra else f"{primary}\n\n{extra}"
    # Offer the wizard as a frictionless alternative.
    msg += "\n\nTip: tap *New Lead Search* below for a step-by-step wizard."
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(),
    )


# --------------------------------------------------------------------------- #
# Catch-all error handler
# --------------------------------------------------------------------------- #


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error in update handler", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, something went wrong. Please try again in a moment."
            )
    except Exception:  # pragma: no cover
        pass
