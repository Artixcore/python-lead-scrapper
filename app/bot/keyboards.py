"""Inline keyboard factories used by the bot.

All callback-data strings use a short ``scope:value`` format so handlers can
route them via simple regex patterns (e.g. ``^type:``).
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# --------------------------------------------------------------------------- #
# Constants (single source of truth)
# --------------------------------------------------------------------------- #

#: Preset business types shown as quick-pick buttons.
#: (display_label, canonical_keyword_for_the_parser)
COMMON_TYPES: list[tuple[str, str]] = [
    ("Dentists", "dentists"),
    ("Restaurants", "restaurants"),
    ("Real Estate", "real estate agencies"),
    ("Software", "software companies"),
    ("Marketing", "marketing agencies"),
    ("Lawyers", "lawyers"),
    ("Accountants", "accountants"),
    ("Hotels", "hotels"),
    ("Cafes", "cafes"),
    ("Gyms", "gyms"),
]

#: Lead-count presets shown as quick-pick buttons.
COUNT_OPTIONS: list[int] = [10, 20, 50, 100]

#: Required-field toggles -- order matters (displayed top to bottom).
REQ_FIELDS: list[tuple[str, str]] = [
    ("website_required", "Website"),
    ("email_required", "Email"),
    ("phone_required", "Phone"),
    ("social_required", "Social"),
]


# --------------------------------------------------------------------------- #
# Keyboards
# --------------------------------------------------------------------------- #


def main_menu_kb() -> InlineKeyboardMarkup:
    """Main menu shown on /start and after a job completes."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("New Lead Search", callback_data="menu:new")],
            [
                InlineKeyboardButton("Examples", callback_data="menu:examples"),
                InlineKeyboardButton("Help", callback_data="menu:help"),
            ],
        ]
    )


def business_type_kb() -> InlineKeyboardMarkup:
    """Grid of common business types plus Custom and Cancel."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for label, value in COMMON_TYPES:
        row.append(InlineKeyboardButton(label, callback_data=f"type:{value}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton("Custom...", callback_data="type:__custom__"),
            InlineKeyboardButton("Cancel", callback_data="wizard:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def count_kb() -> InlineKeyboardMarkup:
    """Row of preset lead counts + Cancel."""
    row = [
        InlineKeyboardButton(str(n), callback_data=f"count:{n}")
        for n in COUNT_OPTIONS
    ]
    return InlineKeyboardMarkup(
        [
            row,
            [InlineKeyboardButton("Cancel", callback_data="wizard:cancel")],
        ]
    )


def requirements_kb(selected: dict[str, bool]) -> InlineKeyboardMarkup:
    """Multi-select checkboxes for required fields.

    ``selected`` maps field name (e.g. ``email_required``) to ``True``/``False``.
    The keyboard is rebuilt on every toggle.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in REQ_FIELDS:
        mark = "[X]" if selected.get(key) else "[ ]"
        rows.append(
            [InlineKeyboardButton(f"{mark} {label}", callback_data=f"req:{key}")]
        )
    rows.append(
        [
            InlineKeyboardButton("Done", callback_data="req:done"),
            InlineKeyboardButton("Cancel", callback_data="wizard:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def confirm_kb() -> InlineKeyboardMarkup:
    """Final confirm / cancel before running the job."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Start Search", callback_data="confirm:go"),
                InlineKeyboardButton("Cancel", callback_data="wizard:cancel"),
            ]
        ]
    )


def after_job_kb() -> InlineKeyboardMarkup:
    """Buttons shown after a job completes."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("New Search", callback_data="menu:new"),
                InlineKeyboardButton("Main Menu", callback_data="menu:main"),
            ]
        ]
    )
