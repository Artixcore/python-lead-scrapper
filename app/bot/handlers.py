"""Telegram handlers -- wired into the Application in ``telegram_bot.py``."""

from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from app.bot import messages
from app.logging_config import get_logger
from app.models.lead_request import LeadRequest
from app.parsing.request_parser import ParseError, parse_request
from app.services.lead_service import LeadService

log = get_logger(__name__)


# Global limit so one user can't kick off dozens of jobs at once.
_JOB_SEMAPHORE = asyncio.Semaphore(4)
# Per-user active jobs (user_id -> count).
_active_jobs: dict[int, int] = {}
_MAX_PER_USER = 1


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(messages.WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(messages.HELP, parse_mode=ParseMode.MARKDOWN)


async def example(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(messages.EXAMPLES, parse_mode=ParseMode.MARKDOWN)


# --------------------------------------------------------------------------- #
# Main message handler
# --------------------------------------------------------------------------- #


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat any non-command text message as a lead request."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id if update.effective_user else None

    # ---- per-user rate guard ----
    if user_id is not None and _active_jobs.get(user_id, 0) >= _MAX_PER_USER:
        await update.message.reply_text(
            "You already have a job running. Please wait for it to finish."
        )
        return

    # ---- parse ----
    try:
        request: LeadRequest = parse_request(text)
    except ParseError as e:
        await _reply_clarification(update, e)
        return

    # ---- kick off job ----
    service: LeadService = context.application.bot_data["lead_service"]

    if user_id is not None:
        _active_jobs[user_id] = _active_jobs.get(user_id, 0) + 1
    try:
        async with _JOB_SEMAPHORE:
            await _run_job(update, context, request, service)
    finally:
        if user_id is not None:
            _active_jobs[user_id] = max(0, _active_jobs.get(user_id, 1) - 1)


# --------------------------------------------------------------------------- #
# Core job flow
# --------------------------------------------------------------------------- #


async def _run_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: LeadRequest,
    service: LeadService,
) -> None:
    assert update.message is not None
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None

    await update.message.reply_text(
        messages.format_acknowledgement(request),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Progress callback posts "typing" + periodic updates.
    async def progress(msg: str) -> None:
        try:
            if chat_id is not None:
                await context.bot.send_chat_action(
                    chat_id=chat_id, action=ChatAction.TYPING
                )
            # Only surface meaningful milestones to avoid chat spam.
            if any(
                msg.startswith(pref)
                for pref in ("Searching", "Deduplicating", "Enriching", "Scoring")
            ):
                await update.message.reply_text(messages.format_progress(msg))
        except Exception:  # pragma: no cover
            log.debug("Progress update failed.")

    try:
        result, csv_path = await service.run(
            request, user_id=user_id, progress=progress
        )
    except Exception as e:
        log.exception("Pipeline failed: %s", e)
        await update.message.reply_text(
            "Sorry, something went wrong while running your request. Please try again."
        )
        return

    # ---- summary ----
    summary = messages.format_summary(result)
    try:
        await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:  # Markdown parsing errors
        log.warning("Summary markdown send failed (%s); sending as plain text.", e)
        await update.message.reply_text(summary)

    # Contextual notes
    if result.total_cleaned == 0:
        await update.message.reply_text(messages.LOW_RESULT_WARNING)
    elif result.total_with_email == 0 and request.email_required:
        await update.message.reply_text(messages.FEW_EMAILS_NOTE)

    # ---- CSV attachment ----
    await _send_csv(update, csv_path)


async def _send_csv(update: Update, csv_path: Path) -> None:
    assert update.message is not None
    try:
        with csv_path.open("rb") as f:
            await update.message.reply_document(
                document=f,
                filename=csv_path.name,
                caption="Full results (CSV)",
            )
    except Exception as e:
        log.warning("Could not send CSV %s: %s", csv_path, e)
        await update.message.reply_text(
            "I generated the CSV but couldn't attach it. "
            f"You can find it on the server at `{csv_path}`.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _reply_clarification(update: Update, err: ParseError) -> None:
    assert update.message is not None
    # Prefer the first clarifying question so the user gets one clean prompt.
    primary = err.issues[0].message
    extra = "\n".join(f"- {i.message}" for i in err.issues[1:])
    msg = primary
    if extra:
        msg = f"{primary}\n\n{extra}"
    await update.message.reply_text(msg)


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
