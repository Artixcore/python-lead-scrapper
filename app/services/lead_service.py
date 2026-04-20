"""High-level lead generation pipeline.

Stages:
  1. Parse request   (done by the bot layer, we accept a LeadRequest)
  2. Validate required fields  (pydantic)
  3. Query source adapters
  4. Merge candidate leads
  5. Deduplicate raw leads
  6. Enrich leads from websites
  7. Validate extracted emails/phones/websites
  8. Score leads
  9. Export CSV (caller's concern)
 10. Send summary + CSV       (bot layer)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import settings
from app.db.sqlite import SQLiteDB
from app.logging_config import get_logger
from app.models.lead import Lead
from app.models.lead_request import LeadRequest
from app.models.scrape_result import ScrapeResult
from app.scraping.base import HTTPClient
from app.scraping.source_manager import SourceManager
from app.scraping.sources.website_enricher import WebsiteEnricher
from app.services.cache_service import CacheService
from app.services.dedupe_service import DedupeService
from app.services.export_service import ExportService
from app.services.progress import Progress, ProgressCb, stage_percent
from app.services.scoring_service import ScoringService
from app.utils.url_tools import normalize_url
from app.utils.validators import (
    is_valid_website,
    normalize_email,
    normalize_phone,
)

log = get_logger(__name__)


class LeadService:
    """Orchestrates the full lead generation pipeline."""

    def __init__(
        self,
        *,
        source_manager: SourceManager,
        enricher: WebsiteEnricher,
        dedupe: DedupeService,
        scorer: ScoringService,
        exporter: ExportService,
        db: SQLiteDB | None = None,
    ) -> None:
        self._sources = source_manager
        self._enricher = enricher
        self._dedupe = dedupe
        self._scorer = scorer
        self._exporter = exporter
        self._db = db

    # ------------------------------------------------------------------ #
    # Public pipeline
    # ------------------------------------------------------------------ #

    async def run(
        self,
        request: LeadRequest,
        *,
        user_id: int | None = None,
        progress: ProgressCb | None = None,
    ) -> tuple[ScrapeResult, Path]:
        """Run the pipeline and return (result, csv_path).

        ``progress`` is an optional async callback that receives
        :class:`Progress` snapshots at every stage (and after each enriched
        lead).  The callback must not raise; if it does, the error is logged
        and the pipeline continues.
        """

        async def _notify(p: Progress) -> None:
            log.info("[%d%%] %s%s", p.percent, p.stage, f" - {p.detail}" if p.detail else "")
            if progress:
                try:
                    await progress(p)
                except Exception:  # pragma: no cover
                    log.debug("Progress callback raised; ignoring.")

        await _notify(Progress(stage_percent("Starting"), "Starting"))

        job_id: int | None = None
        if self._db is not None:
            try:
                job_id = await self._db.create_job(user_id, request)
            except Exception as e:  # pragma: no cover
                log.warning("Could not create job row: %s", e)

        async with HTTPClient() as http:
            await _notify(Progress(stage_percent("Discovering", 0.0), "Discovering", "searching public sources"))
            raw_leads = await self._sources.collect(request, http)
            total_found = len(raw_leads)
            log.info("Discovery: %d raw leads from all sources.", total_found)
            await _notify(
                Progress(
                    stage_percent("Discovering", 1.0),
                    "Discovering",
                    f"{total_found} candidates",
                )
            )

            # Clean + validate before dedupe so dedupe keys are reliable.
            raw_leads = [self._clean_raw_lead(l, request) for l in raw_leads]

            await _notify(
                Progress(
                    stage_percent("Deduplicating", 0.0),
                    "Deduplicating",
                    f"{total_found} candidates",
                )
            )
            deduped = self._dedupe.dedupe(raw_leads)
            log.info("Dedupe: %d unique leads.", len(deduped))
            await _notify(
                Progress(
                    stage_percent("Deduplicating", 1.0),
                    "Deduplicating",
                    f"{len(deduped)} unique",
                )
            )

            # Cap the candidates we bother enriching (save time on huge results).
            enrich_cap = max(request.max_leads * 2, request.max_leads + 10)
            to_enrich = deduped[:enrich_cap]

            enriched = await self._enrich_many(to_enrich, http, _notify)

            # Post-enrichment cleanup (extractor output may need re-normalizing)
            enriched = [self._clean_enriched_lead(l, request) for l in enriched]

            # Apply required-field filters, if requested
            filtered = self._apply_required_filters(enriched, request)

            await _notify(Progress(stage_percent("Scoring", 0.0), "Scoring"))
            self._scorer.score_leads(filtered, request)
            filtered.sort(key=lambda l: l.lead_score, reverse=True)
            await _notify(Progress(stage_percent("Scoring", 1.0), "Scoring"))

            final = filtered[: request.max_leads]

            result = ScrapeResult.build(request=request, found=total_found, leads=final)

        # ---- export + persist ----
        await _notify(
            Progress(
                stage_percent("Exporting", 0.0),
                "Exporting",
                f"{len(final)} leads",
            )
        )
        csv_path = self._exporter.export_leads(final, request)

        if self._db is not None and job_id is not None:
            try:
                await self._db.save_leads(job_id, final)
                await self._db.finish_job(
                    job_id,
                    status="ok" if final else "empty",
                    total_found=total_found,
                    total_cleaned=len(final),
                )
            except Exception as e:  # pragma: no cover
                log.warning("Could not persist job %s: %s", job_id, e)

        await _notify(Progress(100, "Done", f"{len(final)} leads ready"))

        return result, csv_path

    # ------------------------------------------------------------------ #
    # Stages
    # ------------------------------------------------------------------ #

    async def _enrich_many(
        self,
        leads: list[Lead],
        http: HTTPClient,
        notify: ProgressCb | None = None,
    ) -> list[Lead]:
        """Enrich leads concurrently, respecting the shared rate limiter.

        Fires per-completion progress updates via ``notify`` so the caller can
        redraw a progress bar in real time.  Order of returned leads matches
        the input order.
        """
        if not leads:
            if notify:
                await notify(
                    Progress(stage_percent("Enriching", 1.0), "Enriching", "0 websites")
                )
            return []

        semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        total = len(leads)

        async def _task(idx: int, l: Lead) -> tuple[int, Lead]:
            async with semaphore:
                try:
                    out = await self._enricher.enrich(l, http)
                except Exception as e:  # pragma: no cover
                    log.debug("Enrichment error for %r: %s", l.company_name, e)
                    out = l
            return idx, out

        if notify:
            await notify(
                Progress(
                    stage_percent("Enriching", 0.0),
                    "Enriching",
                    f"0 / {total} websites",
                )
            )

        results: list[Lead | None] = [None] * total
        tasks = [asyncio.create_task(_task(i, l)) for i, l in enumerate(leads)]
        done = 0
        for coro in asyncio.as_completed(tasks):
            idx, out = await coro
            results[idx] = out
            done += 1
            if notify:
                await notify(
                    Progress(
                        stage_percent("Enriching", done / total),
                        "Enriching",
                        f"{done} / {total} websites",
                    )
                )

        return [l for l in results if l is not None]

    def _clean_raw_lead(self, lead: Lead, request: LeadRequest) -> Lead:
        """Normalize obvious fields on a freshly-discovered lead."""
        lead.website = normalize_url(lead.website) if lead.website else None
        if lead.email:
            lead.email = normalize_email(lead.email)
        if lead.phone:
            lead.phone = normalize_phone(lead.phone, _region_from_country(request.country)) or lead.phone
        # Fill location defaults from the request when missing.
        if not lead.city:
            lead.city = request.city
        if not lead.state_or_region:
            lead.state_or_region = request.state_or_region
        if not lead.country:
            lead.country = request.country
        return lead

    def _clean_enriched_lead(self, lead: Lead, request: LeadRequest) -> Lead:
        """Clean up values written by enrichment extractors."""
        if lead.website and not is_valid_website(lead.website):
            lead.website = None
        if lead.email:
            lead.email = normalize_email(lead.email)
        if lead.phone:
            lead.phone = (
                normalize_phone(lead.phone, _region_from_country(request.country))
                or lead.phone
            )
        return lead

    def _apply_required_filters(
        self,
        leads: list[Lead],
        request: LeadRequest,
    ) -> list[Lead]:
        """Drop leads that fail user-specified must-have fields."""
        def keep(l: Lead) -> bool:
            if request.website_required and not l.website:
                return False
            if request.email_required and not l.email:
                return False
            if request.phone_required and not l.phone:
                return False
            if request.social_required and not l.any_social():
                return False
            return True

        return [l for l in leads if keep(l)]


def _region_from_country(country: str | None) -> str | None:
    # Keep this in sync with WebsiteEnricher._COUNTRY_TO_REGION for consistency.
    from app.scraping.sources.website_enricher import _COUNTRY_TO_REGION

    if not country:
        return None
    return _COUNTRY_TO_REGION.get(country.strip())


def build_default_lead_service(db: SQLiteDB | None = None) -> LeadService:
    """Factory that wires up the default pipeline."""
    from app.scraping.sources.osm_source import OSMSource
    from app.scraping.sources.directory_source import DirectorySource

    manager = SourceManager()
    manager.register(OSMSource())
    manager.register(DirectorySource())

    cache = CacheService(db) if db is not None else None
    enricher = WebsiteEnricher(cache=cache)

    return LeadService(
        source_manager=manager,
        enricher=enricher,
        dedupe=DedupeService(),
        scorer=ScoringService(),
        exporter=ExportService(),
        db=db,
    )
