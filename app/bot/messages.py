"""Static / formatted Telegram messages."""

from __future__ import annotations

from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.models.scrape_result import ScrapeResult


WELCOME = (
    "Hi! I am a lead-generation bot. \n\n"
    "Tell me what kind of businesses you want to find and where. Examples:\n"
    "  - Find 20 dentists in Dallas with email and website\n"
    "  - Find real estate agencies in London\n"
    "  - Get 50 software companies in Berlin with phone numbers\n"
    "  - Need restaurants in Paris\n\n"
    "Send /help for more details or /example for sample queries."
)

HELP = (
    "*How to use this bot*\n\n"
    "Send a message describing the leads you want. I will:\n"
    "1. Parse your request\n"
    "2. Search public sources (OpenStreetMap by default)\n"
    "3. Visit each business website to find public emails/phones/socials\n"
    "4. Return a summary + a CSV file with the full dataset\n\n"
    "*Tips*\n"
    "- Include a city or country (required)\n"
    "- You can say 'with email and website' to filter\n"
    "- Ask for a specific count: 'Find 30 cafes in Paris'\n\n"
    "I only collect publicly visible data. I do not bypass logins, paywalls, or CAPTCHAs."
)

EXAMPLES = (
    "*Example requests*\n\n"
    "  - Find 20 dentists in Dallas with email and website\n"
    "  - Find real estate agencies in London\n"
    "  - Get 50 software companies in Berlin with phone numbers\n"
    "  - Need restaurants in Paris\n"
    "  - Find 30 marketing agencies in New York with social media\n"
)

UNKNOWN_INPUT = (
    "I couldn't understand your request. Try something like:\n"
    "  - Find 20 dentists in Dallas with email and website"
)


def format_acknowledgement(request: LeadRequest) -> str:
    """Message sent right after successfully parsing the user's query."""
    loc = request.location_string() or "(anywhere)"
    return (
        f"Got it. Searching for *{request.keyword}* in *{loc}*. "
        "This may take a moment."
    )


def format_progress(stage: str) -> str:
    return f"{stage}"


def format_summary(result: ScrapeResult) -> str:
    """Human-friendly summary sent after the job completes."""
    req = result.request
    loc = req.location_string() or "(anywhere)"

    lines = [
        f"*Query:* {req.max_leads} {req.keyword} in {loc}",
        f"*Candidates found:* {result.total_found}",
        f"*Leads returned:* {result.total_cleaned}",
        f"  - with website: {result.total_with_website}",
        f"  - with email:   {result.total_with_email}",
        f"  - with phone:   {result.total_with_phone}",
    ]

    if result.leads:
        lines.append("")
        lines.append("*Top 5 sample leads:*")
        for i, lead in enumerate(result.leads[:5], start=1):
            lines.append(_format_sample_lead(i, lead))
    else:
        lines.append("")
        lines.append("No leads matched your criteria.")

    return "\n".join(lines)


def _format_sample_lead(idx: int, lead: Lead) -> str:
    bits = [f"{idx}. *{_md_escape(lead.company_name)}*"]
    if lead.category:
        bits.append(f"  - {lead.category}")
    if lead.website:
        bits.append(f"  - {lead.website}")
    if lead.email:
        bits.append(f"  - {lead.email}")
    if lead.phone:
        bits.append(f"  - {lead.phone}")
    if lead.address:
        bits.append(f"  - {_md_escape(lead.address)}")
    bits.append(f"  - score: {lead.lead_score}")
    return "\n".join(bits)


def _md_escape(s: str | None) -> str:
    if not s:
        return ""
    # Very light Markdown V1 escape (we use ParseMode.MARKDOWN).
    for ch in ("*", "_", "`", "["):
        s = s.replace(ch, f"\\{ch}")
    return s


# ---- contextual messages ----

LOW_RESULT_WARNING = (
    "I couldn't find enough leads for that query. "
    "Try broadening the location or removing strict filters (like 'with email')."
)

FEW_EMAILS_NOTE = (
    "I found some leads, but only a few had public emails. "
    "Many small businesses don't publish email addresses on their website."
)

NEED_LOCATION = "Please include a city or country in your request."
NEED_KEYWORD = "What type of business leads do you need?"
