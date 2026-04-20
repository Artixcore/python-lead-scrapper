"""Lookups for industry/country normalization used by the parser."""

from __future__ import annotations

# ---- keyword -> industry ----
# Very simple; intended as a sensible starting mapping.
INDUSTRY_MAP: dict[str, str] = {
    # healthcare
    "dentist": "healthcare",
    "dentists": "healthcare",
    "doctor": "healthcare",
    "doctors": "healthcare",
    "clinic": "healthcare",
    "clinics": "healthcare",
    "hospital": "healthcare",
    "hospitals": "healthcare",
    "pharmacy": "healthcare",
    "pharmacies": "healthcare",
    "veterinarian": "healthcare",
    "vets": "healthcare",
    "vet": "healthcare",
    "physiotherapist": "healthcare",
    # real estate
    "real estate": "real_estate",
    "realtor": "real_estate",
    "realtors": "real_estate",
    "real estate agent": "real_estate",
    "real estate agents": "real_estate",
    "real estate agency": "real_estate",
    "real estate agencies": "real_estate",
    "estate agent": "real_estate",
    "estate agents": "real_estate",
    # software / tech
    "software company": "technology",
    "software companies": "technology",
    "software": "technology",
    "saas": "technology",
    "tech company": "technology",
    "tech companies": "technology",
    "it company": "technology",
    "it companies": "technology",
    # marketing
    "marketing agency": "marketing",
    "marketing agencies": "marketing",
    "digital agency": "marketing",
    "advertising agency": "marketing",
    "advertising agencies": "marketing",
    "seo agency": "marketing",
    "seo agencies": "marketing",
    # food & hospitality
    "restaurant": "food",
    "restaurants": "food",
    "cafe": "food",
    "cafes": "food",
    "coffee shop": "food",
    "bar": "food",
    "bars": "food",
    "bakery": "food",
    "bakeries": "food",
    "hotel": "hospitality",
    "hotels": "hospitality",
    # retail / services
    "gym": "fitness",
    "gyms": "fitness",
    "salon": "services",
    "salons": "services",
    "barber": "services",
    "barbers": "services",
    "plumber": "services",
    "plumbers": "services",
    "electrician": "services",
    "electricians": "services",
    # legal / finance
    "lawyer": "legal",
    "lawyers": "legal",
    "attorney": "legal",
    "attorneys": "legal",
    "law firm": "legal",
    "law firms": "legal",
    "accountant": "finance",
    "accountants": "finance",
    "accounting firm": "finance",
    "accounting firms": "finance",
}


# ---- keyword -> canonical business_type ----
# Used mainly to feed OSM adapters.
BUSINESS_TYPE_MAP: dict[str, str] = {
    "dentist": "dentist",
    "dentists": "dentist",
    "doctor": "doctors",
    "doctors": "doctors",
    "clinic": "clinic",
    "clinics": "clinic",
    "hospital": "hospital",
    "hospitals": "hospital",
    "pharmacy": "pharmacy",
    "pharmacies": "pharmacy",
    "vet": "veterinary",
    "vets": "veterinary",
    "veterinarian": "veterinary",
    "real estate": "real_estate_agency",
    "real estate agent": "real_estate_agency",
    "real estate agents": "real_estate_agency",
    "real estate agency": "real_estate_agency",
    "real estate agencies": "real_estate_agency",
    "realtor": "real_estate_agency",
    "realtors": "real_estate_agency",
    "estate agent": "real_estate_agency",
    "estate agents": "real_estate_agency",
    "software company": "it_company",
    "software companies": "it_company",
    "software": "it_company",
    "tech company": "it_company",
    "tech companies": "it_company",
    "it company": "it_company",
    "it companies": "it_company",
    "marketing agency": "marketing_agency",
    "marketing agencies": "marketing_agency",
    "digital agency": "marketing_agency",
    "advertising agency": "advertising_agency",
    "advertising agencies": "advertising_agency",
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "cafe": "cafe",
    "cafes": "cafe",
    "coffee shop": "cafe",
    "bar": "bar",
    "bars": "bar",
    "bakery": "bakery",
    "bakeries": "bakery",
    "hotel": "hotel",
    "hotels": "hotel",
    "gym": "fitness_centre",
    "gyms": "fitness_centre",
    "salon": "hairdresser",
    "salons": "hairdresser",
    "barber": "hairdresser",
    "barbers": "hairdresser",
    "plumber": "plumber",
    "plumbers": "plumber",
    "electrician": "electrician",
    "electricians": "electrician",
    "lawyer": "lawyer",
    "lawyers": "lawyer",
    "attorney": "lawyer",
    "attorneys": "lawyer",
    "law firm": "lawyer",
    "law firms": "lawyer",
    "accountant": "accountant",
    "accountants": "accountant",
    "accounting firm": "accountant",
    "accounting firms": "accountant",
}


# ---- Known US states -> canonical name (small starter set) ----
# Used when parser sees a US city but the user didn't mention the state.
US_CITY_TO_STATE: dict[str, str] = {
    "dallas": "Texas",
    "houston": "Texas",
    "austin": "Texas",
    "san antonio": "Texas",
    "new york": "New York",
    "nyc": "New York",
    "brooklyn": "New York",
    "queens": "New York",
    "los angeles": "California",
    "san francisco": "California",
    "san diego": "California",
    "sacramento": "California",
    "oakland": "California",
    "chicago": "Illinois",
    "miami": "Florida",
    "orlando": "Florida",
    "tampa": "Florida",
    "jacksonville": "Florida",
    "boston": "Massachusetts",
    "seattle": "Washington",
    "portland": "Oregon",
    "denver": "Colorado",
    "phoenix": "Arizona",
    "las vegas": "Nevada",
    "atlanta": "Georgia",
    "philadelphia": "Pennsylvania",
    "pittsburgh": "Pennsylvania",
    "detroit": "Michigan",
    "minneapolis": "Minnesota",
    "nashville": "Tennessee",
    "memphis": "Tennessee",
    "washington": "District of Columbia",
    "dc": "District of Columbia",
}


# City -> country (tiny starter set). The goal is: if the user says "Paris",
# we infer France unless otherwise specified.
CITY_TO_COUNTRY: dict[str, str] = {
    # US
    **{c: "USA" for c in US_CITY_TO_STATE.keys()},
    # UK
    "london": "United Kingdom",
    "manchester": "United Kingdom",
    "birmingham": "United Kingdom",
    "liverpool": "United Kingdom",
    "edinburgh": "United Kingdom",
    "glasgow": "United Kingdom",
    # France
    "paris": "France",
    "lyon": "France",
    "marseille": "France",
    "toulouse": "France",
    "nice": "France",
    # Germany
    "berlin": "Germany",
    "munich": "Germany",
    "hamburg": "Germany",
    "frankfurt": "Germany",
    "cologne": "Germany",
    # Other EU
    "amsterdam": "Netherlands",
    "rotterdam": "Netherlands",
    "brussels": "Belgium",
    "madrid": "Spain",
    "barcelona": "Spain",
    "rome": "Italy",
    "milan": "Italy",
    "vienna": "Austria",
    "zurich": "Switzerland",
    "dublin": "Ireland",
    "lisbon": "Portugal",
    "stockholm": "Sweden",
    "copenhagen": "Denmark",
    "oslo": "Norway",
    "helsinki": "Finland",
    "warsaw": "Poland",
    "prague": "Czechia",
    # APAC
    "tokyo": "Japan",
    "osaka": "Japan",
    "seoul": "South Korea",
    "singapore": "Singapore",
    "hong kong": "Hong Kong",
    "sydney": "Australia",
    "melbourne": "Australia",
    "mumbai": "India",
    "delhi": "India",
    "bangalore": "India",
    # Americas
    "toronto": "Canada",
    "vancouver": "Canada",
    "montreal": "Canada",
    "mexico city": "Mexico",
    "sao paulo": "Brazil",
    "buenos aires": "Argentina",
}


# Country aliases -> canonical
COUNTRY_ALIASES: dict[str, str] = {
    "usa": "USA",
    "us": "USA",
    "u.s.": "USA",
    "u.s.a.": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "america": "USA",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "uae": "United Arab Emirates",
}


def industry_for(keyword: str) -> str | None:
    """Best-effort industry lookup for a keyword."""
    k = keyword.strip().lower()
    if k in INDUSTRY_MAP:
        return INDUSTRY_MAP[k]
    # try stripping trailing 's'
    if k.endswith("s") and k[:-1] in INDUSTRY_MAP:
        return INDUSTRY_MAP[k[:-1]]
    return None


def business_type_for(keyword: str) -> str | None:
    """Best-effort canonical business type for a keyword."""
    k = keyword.strip().lower()
    if k in BUSINESS_TYPE_MAP:
        return BUSINESS_TYPE_MAP[k]
    if k.endswith("s") and k[:-1] in BUSINESS_TYPE_MAP:
        return BUSINESS_TYPE_MAP[k[:-1]]
    return None


def normalize_country(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    return COUNTRY_ALIASES.get(key, name.strip().title())


def infer_country_from_city(city: str | None) -> str | None:
    if not city:
        return None
    return CITY_TO_COUNTRY.get(city.strip().lower())


def infer_state_from_city(city: str | None) -> str | None:
    if not city:
        return None
    return US_CITY_TO_STATE.get(city.strip().lower())
