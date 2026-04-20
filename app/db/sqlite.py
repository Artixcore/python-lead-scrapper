"""Small async-friendly SQLite helper.

Uses the built-in stdlib ``sqlite3`` module via ``asyncio.to_thread`` to avoid
pulling an extra aiosqlite dependency. Fine for this bot's modest load.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import settings
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest

log = get_logger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    request_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_found INTEGER DEFAULT 0,
    total_cleaned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    company_name TEXT NOT NULL,
    category TEXT,
    website TEXT,
    email TEXT,
    phone TEXT,
    contact_page TEXT,
    city TEXT,
    state_or_region TEXT,
    country TEXT,
    address TEXT,
    source_name TEXT,
    source_url TEXT,
    linkedin_url TEXT,
    facebook_url TEXT,
    instagram_url TEXT,
    twitter_url TEXT,
    description TEXT,
    lead_score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    scraped_at TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_job ON leads(job_id);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company_name);

CREATE TABLE IF NOT EXISTS page_cache (
    url TEXT PRIMARY KEY,
    html TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


class SQLiteDB:
    """Thin async wrapper around an sqlite3 database."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else settings.sqlite_path_resolved
        self._lock = asyncio.Lock()  # ensure serialized writes

    # ---------------- lifecycle ---------------- #

    async def init(self) -> None:
        """Create tables if they don't exist."""
        def _init() -> None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(SCHEMA_SQL)
                conn.commit()

        await asyncio.to_thread(_init)
        log.info("SQLite initialized at %s", self._path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # ---------------- jobs ---------------- #

    async def create_job(self, user_id: int | None, request: LeadRequest) -> int:
        now = _utcnow_iso()
        payload = request.model_dump_json()

        def _do() -> int:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO jobs(user_id, request_json, status, created_at) "
                    "VALUES (?, ?, 'pending', ?)",
                    (user_id, payload, now),
                )
                conn.commit()
                return int(cur.lastrowid)

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def finish_job(
        self,
        job_id: int,
        *,
        status: str,
        total_found: int,
        total_cleaned: int,
    ) -> None:
        now = _utcnow_iso()

        def _do() -> None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET status=?, total_found=?, total_cleaned=?, "
                    "completed_at=? WHERE id=?",
                    (status, total_found, total_cleaned, now, job_id),
                )
                conn.commit()

        async with self._lock:
            await asyncio.to_thread(_do)

    # ---------------- leads ---------------- #

    async def save_leads(self, job_id: int, leads: Iterable[Lead]) -> int:
        rows = [_lead_row(l, job_id) for l in leads]
        if not rows:
            return 0

        def _do() -> int:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO leads(
                        job_id, company_name, category, website, email, phone,
                        contact_page, city, state_or_region, country, address,
                        source_name, source_url, linkedin_url, facebook_url,
                        instagram_url, twitter_url, description, lead_score,
                        status, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
                return len(rows)

        async with self._lock:
            return await asyncio.to_thread(_do)

    # ---------------- cache ---------------- #

    async def cache_get(self, url: str) -> str | None:
        def _do() -> str | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT html FROM page_cache WHERE url=?", (url,)
                ).fetchone()
                return row["html"] if row else None

        return await asyncio.to_thread(_do)

    async def cache_set(self, url: str, html: str) -> None:
        now = _utcnow_iso()

        def _do() -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO page_cache(url, html, fetched_at) "
                    "VALUES (?, ?, ?)",
                    (url, html, now),
                )
                conn.commit()

        async with self._lock:
            await asyncio.to_thread(_do)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lead_row(lead: Lead, job_id: int) -> tuple[Any, ...]:
    return (
        job_id,
        lead.company_name,
        lead.category,
        lead.website,
        lead.email,
        lead.phone,
        lead.contact_page,
        lead.city,
        lead.state_or_region,
        lead.country,
        lead.address,
        lead.source_name,
        lead.source_url,
        lead.linkedin_url,
        lead.facebook_url,
        lead.instagram_url,
        lead.twitter_url,
        lead.description,
        lead.lead_score,
        lead.status,
        lead.scraped_at.isoformat(),
    )
