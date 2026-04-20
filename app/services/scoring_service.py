"""Compute a 0-100 lead_score for each lead."""

from __future__ import annotations

from app.models.lead import Lead
from app.models.lead_request import LeadRequest


# Scoring weights (sum can exceed 100; clamped at 100)
W_WEBSITE = 25
W_EMAIL = 25
W_PHONE = 15
W_CONTACT = 10
W_SOCIAL = 10
W_CATEGORY_MATCH = 15


class ScoringService:
    """Assigns `lead_score` on a 0..100 scale."""

    def score_leads(self, leads: list[Lead], request: LeadRequest) -> list[Lead]:
        for lead in leads:
            lead.lead_score = self._score_one(lead, request)
        return leads

    def _score_one(self, lead: Lead, request: LeadRequest) -> int:
        score = 0
        if lead.website:
            score += W_WEBSITE
        if lead.email:
            score += W_EMAIL
        if lead.phone:
            score += W_PHONE
        if lead.contact_page:
            score += W_CONTACT
        if lead.any_social():
            score += W_SOCIAL
        if self._category_matches(lead, request):
            score += W_CATEGORY_MATCH

        return max(0, min(100, score))

    def _category_matches(self, lead: Lead, request: LeadRequest) -> bool:
        """Is the lead's category a strong match for the requested type?"""
        bt = (request.business_type or "").lower()
        kw = (request.keyword or "").lower()
        cat = (lead.category or "").lower()
        if not cat:
            return False

        needles = {bt, kw}
        # Also compare against just the suffix (e.g. "amenity:dentist" -> "dentist")
        if ":" in cat:
            cat_tail = cat.split(":", 1)[1]
            for n in list(needles):
                if n and (n == cat_tail or n in cat_tail):
                    return True
        for n in needles:
            if n and n in cat:
                return True
        return False
