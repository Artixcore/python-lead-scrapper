"""Lead model -- a single business/contact record."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """A single lead / business record returned to the user."""

    company_name: str = Field(..., description="Display name for the business")
    category: str | None = None

    website: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_page: str | None = None

    city: str | None = None
    state_or_region: str | None = None
    country: str | None = None
    address: str | None = None

    source_name: str | None = None
    source_url: str | None = None

    linkedin_url: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None

    description: str | None = None

    lead_score: int = 0
    status: str = "new"
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- helpers ----

    def has_contact(self) -> bool:
        """Whether the lead has at least one usable contact channel."""
        return bool(self.email or self.phone or self.website)

    def any_social(self) -> bool:
        return any(
            [self.linkedin_url, self.facebook_url, self.instagram_url, self.twitter_url]
        )

    def to_csv_row(self) -> dict[str, str | int | None]:
        """Return a flat dict suitable for CSV export."""
        return {
            "company_name": self.company_name,
            "category": self.category,
            "website": self.website,
            "email": self.email,
            "phone": self.phone,
            "contact_page": self.contact_page,
            "city": self.city,
            "state_or_region": self.state_or_region,
            "country": self.country,
            "address": self.address,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "linkedin_url": self.linkedin_url,
            "facebook_url": self.facebook_url,
            "instagram_url": self.instagram_url,
            "twitter_url": self.twitter_url,
            "description": self.description,
            "lead_score": self.lead_score,
            "status": self.status,
            "scraped_at": self.scraped_at.isoformat(),
        }
