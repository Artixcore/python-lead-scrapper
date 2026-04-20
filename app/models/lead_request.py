"""Structured representation of a user's lead request."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LeadRequest(BaseModel):
    """Structured user request parsed from a free-text Telegram message."""

    keyword: str = Field(..., description="Primary search keyword, e.g. 'dentists'")
    business_type: str | None = Field(default=None)
    industry: str | None = Field(default=None)

    city: str | None = Field(default=None)
    state_or_region: str | None = Field(default=None)
    country: str | None = Field(default=None)

    max_leads: int = Field(default=20, ge=1, le=1000)

    website_required: bool = False
    email_required: bool = False
    phone_required: bool = False
    social_required: bool = False

    notes: str = ""

    # ----- validation -----

    @field_validator("keyword", mode="before")
    @classmethod
    def _strip_keyword(cls, v: str) -> str:
        if not isinstance(v, str):
            raise TypeError("keyword must be a string")
        v = v.strip()
        if not v:
            raise ValueError("keyword cannot be empty")
        return v

    # ----- convenience -----

    def location_string(self) -> str:
        """Return a human-readable location string (may be empty)."""
        parts = [p for p in [self.city, self.state_or_region, self.country] if p]
        return ", ".join(parts)

    def has_location(self) -> bool:
        return any([self.city, self.state_or_region, self.country])

    def pretty(self) -> str:
        """Concise single-line summary of the request."""
        loc = self.location_string() or "(anywhere)"
        reqs: list[str] = []
        if self.website_required:
            reqs.append("website")
        if self.email_required:
            reqs.append("email")
        if self.phone_required:
            reqs.append("phone")
        if self.social_required:
            reqs.append("socials")
        req_str = f" with {', '.join(reqs)}" if reqs else ""
        return f"{self.max_leads} {self.keyword} in {loc}{req_str}"
