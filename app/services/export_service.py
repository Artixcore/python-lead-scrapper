"""CSV export for ``ScrapeResult``."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import settings
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest

log = get_logger(__name__)


_CSV_COLUMNS = [
    "company_name",
    "category",
    "website",
    "email",
    "phone",
    "contact_page",
    "city",
    "state_or_region",
    "country",
    "address",
    "source_name",
    "source_url",
    "linkedin_url",
    "facebook_url",
    "instagram_url",
    "twitter_url",
    "description",
    "lead_score",
    "status",
    "scraped_at",
]


class ExportService:
    """Writes leads to CSV on disk."""

    def __init__(self, export_dir: Path | str | None = None) -> None:
        self._dir = Path(export_dir) if export_dir else settings.export_dir_resolved
        self._dir.mkdir(parents=True, exist_ok=True)

    def export_leads(
        self,
        leads: list[Lead],
        request: LeadRequest,
    ) -> Path:
        """Write ``leads`` to a CSV file and return its path."""
        filename = self._build_filename(request)
        path = self._dir / filename

        if not leads:
            # Still write an empty CSV with headers, so the bot can tell the
            # user a real file was produced.
            pd.DataFrame(columns=_CSV_COLUMNS).to_csv(path, index=False)
            log.info("Exported empty CSV to %s", path)
            return path

        rows = [l.to_csv_row() for l in leads]
        df = pd.DataFrame(rows)
        # Ensure consistent column order even if some leads miss fields.
        for col in _CSV_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[_CSV_COLUMNS]
        df.to_csv(path, index=False)
        log.info("Exported %d leads to %s", len(leads), path)
        return path

    def _build_filename(self, request: LeadRequest) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = _slug(request.keyword or "leads")
        loc_slug = _slug(request.city or request.country or "any")
        return f"leads_{slug}_{loc_slug}_{ts}.csv"


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "leads"
