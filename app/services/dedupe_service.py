"""Lead deduplication utilities."""

from __future__ import annotations

from app.models.lead import Lead
from app.utils.text_tools import slugify_name
from app.utils.url_tools import get_domain


def _normalize_address(addr: str | None) -> str | None:
    if not addr:
        return None
    return " ".join(addr.lower().split())


def _lead_keys(lead: Lead) -> list[str]:
    """Produce one or more dedup keys for a lead."""
    keys: list[str] = []

    name_slug = slugify_name(lead.company_name) or ""
    domain = get_domain(lead.website) or ""
    city_slug = slugify_name(lead.city) or ""

    # Strong key: website domain alone (two leads with same website => same biz)
    if domain:
        keys.append(f"domain:{domain}")

    # Name + city pair
    if name_slug and city_slug:
        keys.append(f"name_city:{name_slug}|{city_slug}")

    # Name + phone pair
    if name_slug and lead.phone:
        keys.append(f"name_phone:{name_slug}|{lead.phone}")

    # Name + address pair
    if name_slug and lead.address:
        keys.append(f"name_addr:{name_slug}|{_normalize_address(lead.address)}")

    return keys


def _merge_into(existing: Lead, new: Lead) -> None:
    """Fill missing fields on ``existing`` using values from ``new``."""
    for field in (
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
    ):
        cur = getattr(existing, field)
        if cur in (None, "", 0):
            new_val = getattr(new, field)
            if new_val not in (None, "", 0):
                setattr(existing, field, new_val)


class DedupeService:
    """Deduplicates leads and merges overlapping field data."""

    def dedupe(self, leads: list[Lead]) -> list[Lead]:
        """Return a deduplicated, merged list of leads (order preserved)."""
        if not leads:
            return []

        by_key: dict[str, Lead] = {}
        unique: list[Lead] = []

        for lead in leads:
            keys = _lead_keys(lead)
            existing: Lead | None = None
            for k in keys:
                if k in by_key:
                    existing = by_key[k]
                    break
            if existing is not None:
                _merge_into(existing, lead)
                # ensure new keys also map to the canonical lead
                for k in keys:
                    by_key.setdefault(k, existing)
            else:
                unique.append(lead)
                for k in keys:
                    by_key.setdefault(k, lead)

        return unique
