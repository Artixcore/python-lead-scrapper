"""Result of a scraping job."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.lead import Lead
from app.models.lead_request import LeadRequest


class ScrapeResult(BaseModel):
    """Result returned from the lead-generation pipeline."""

    request: LeadRequest
    total_found: int = 0
    total_cleaned: int = 0
    total_with_email: int = 0
    total_with_phone: int = 0
    total_with_website: int = 0
    leads: list[Lead] = Field(default_factory=list)

    @classmethod
    def build(cls, request: LeadRequest, found: int, leads: list[Lead]) -> "ScrapeResult":
        """Compute aggregate counts from a final list of leads."""
        return cls(
            request=request,
            total_found=found,
            total_cleaned=len(leads),
            total_with_email=sum(1 for l in leads if l.email),
            total_with_phone=sum(1 for l in leads if l.phone),
            total_with_website=sum(1 for l in leads if l.website),
            leads=leads,
        )
