# Telegram Lead Generation Bot

A production-structured, modular Python Telegram bot that accepts natural-language
lead requests (e.g. *"Find 50 dentists in Dallas with email and website"*),
discovers public business data from free/open sources (primarily OpenStreetMap),
enriches results by visiting business websites for public contact details, scores
and deduplicates the leads, and returns the cleaned dataset plus a CSV file
back to the user in Telegram.

---

## What it does

1. Listens for user messages via a Telegram bot.
2. Parses the natural-language request into a structured `LeadRequest`.
3. Queries multiple public business / place sources in parallel (see
   [Sources](#sources) below).
4. Visits each business's public website (homepage + contact/about pages).
5. Extracts publicly visible emails, phone numbers, social links, and metadata.
6. Cleans, normalizes, deduplicates, and scores every lead.
7. Replies with a concise summary and attaches a full CSV.

Only publicly visible data from legal/compliant sources is collected by
default. The bot does NOT bypass authentication, paywalls, anti-bot measures,
or CAPTCHAs.

---

## Quick start

### 1. Requirements

- Python 3.11 or newer. **Python 3.11 - 3.13 is recommended** for the smoothest
  install (prebuilt wheels for `pydantic-core` and `lxml` exist for every major
  OS). Python 3.14 is supported but requires the newer package versions in
  `requirements.txt` -- older pinned versions don't have 3.14 wheels yet.
- A Telegram Bot token (see below)

#### Note on `lxml` (optional)

The HTML parsing layer will use `lxml` if it's installed (faster) but falls
back to the stdlib `html.parser` automatically if it's not. If `pip install
lxml` fails on your machine (it requires a C compiler on some platforms), you
can safely **comment it out** in `requirements.txt` and the bot will still
work.

### 2. Create a Telegram bot

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the token BotFather gives you.

### 3. Install

```bash
git clone <your-fork-url> lead-gen-bot
cd lead-gen-bot

python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows PowerShell / CMD

pip install -r requirements.txt
```

### 4. Configure

```bash
cp .env.example .env
# then edit .env and set TELEGRAM_BOT_TOKEN=...
```

### 5. Run

```bash
python -m app.main
```

You should see a log line like `Bot started. Listening for updates...`

### 6. Use

Open your bot in Telegram and send e.g.:

- `Find 20 dentists in Dallas with email and website`
- `Find real estate agencies in London`
- `Get 50 software companies in Berlin with phone numbers`
- `Need restaurants in Paris`

---

## Project structure

```
project_root/
  app/
    main.py                 # Entrypoint
    config.py               # Env-based config (pydantic-settings)
    logging_config.py       # Logging setup
    bot/                    # Telegram bot layer
      telegram_bot.py
      handlers.py
      messages.py
    parsing/                # Natural-language request parsing
      request_parser.py
      normalizers.py
    scraping/               # Scraping layer
      base.py               # Source adapter interface
      source_manager.py     # Orchestrates multiple sources
      sources/
        osm_source.py           # OSM Overpass (tag-based)
        nominatim_poi_source.py # Nominatim free-text POI search
        wikidata_source.py      # Wikidata SPARQL
        yelp_source.py          # Yelp Fusion (optional key)
        here_source.py          # HERE Places (optional key)
        foursquare_source.py    # Foursquare Places v3 (optional key)
        google_maps_source.py   # Google local-pack scraper (opt-in)
        website_enricher.py
        directory_source.py
        _geocoder.py            # Shared Nominatim lat/lon cache
      extractors/
        email_extractor.py
        phone_extractor.py
        social_extractor.py
        contact_page_finder.py
    models/                 # Pydantic models
      lead.py
      lead_request.py
      scrape_result.py
    services/               # Business logic
      lead_service.py       # Pipeline orchestration
      scoring_service.py
      dedupe_service.py
      export_service.py
      cache_service.py
    db/
      sqlite.py             # Async SQLite helper
    utils/
      validators.py
      url_tools.py
      text_tools.py
      rate_limiter.py
      retries.py
    tests/                  # pytest tests
      test_parser.py
      test_extractors.py
      test_dedupe.py
  .env.example
  requirements.txt
  README.md
```

---

## Sources

The bot runs every registered source concurrently, merges the candidates,
deduplicates them, and then enriches each one. Add or remove sources via
environment variables; keyless sources always run, keyed sources auto-register
only when their key is present.

| Source              | Needs key? | Env var              | Free tier / notes                                      |
|---------------------|------------|----------------------|--------------------------------------------------------|
| OpenStreetMap       | no         | -                    | Overpass query by OSM tag; global coverage, varies     |
| Nominatim POI       | no         | -                    | Free-text POI search; complements OSM for fuzzy terms  |
| Wikidata SPARQL     | no         | -                    | Notable organizations only; no coverage for SMBs       |
| Yelp Fusion         | **yes**    | `YELP_API_KEY`       | 500 calls/day free; best for US/CA/AU                  |
| HERE Places         | **yes**    | `HERE_API_KEY`       | ~250k transactions/month free; global                  |
| Foursquare Places   | **yes**    | `FOURSQUARE_API_KEY` | Generous free tier; rich socials/phone/website fields  |
| Google Maps (scrape)| no (opt-in)| `ENABLE_GOOGLE_MAPS` | **Off by default** - see warning below                 |

Get API keys from:

- Yelp: <https://docs.developer.yelp.com/docs/fusion-intro>
- HERE: <https://developer.here.com/>
- Foursquare: <https://location.foursquare.com/developer/>

### Google Maps scraping disclaimer

Enabling `ENABLE_GOOGLE_MAPS=true` tells the bot to scrape Google's local-
search HTML. This has two significant caveats:

1. **Google's Terms of Service forbid automated scraping.** Use at your own
   legal risk. The official Google Places API is the only compliant path; if
   you have a Places API key, consider wiring a new adapter that calls it
   instead.
2. **Google changes its HTML frequently.** The scraper is defensive (returns
   zero leads with a warning log on layout drift rather than crashing), but
   expect it to break periodically and require maintenance.

The source is **off by default**. All other sources above work without it.

---

## Example commands (Telegram)

| Command | What happens |
|---------|-------------|
| `/start` | Friendly intro |
| `/help`  | Usage help |
| `/example` | Shows copy-paste example queries |
| *free text* | Treated as a lead request |

---

## Running the tests

```bash
pytest -q
```

---

## Data output (CSV columns)

`company_name, category, website, email, phone, contact_page, city,
state_or_region, country, address, source_name, source_url, linkedin_url,
facebook_url, instagram_url, twitter_url, description, lead_score, status,
scraped_at`

---

## Limitations

- **Only public data.** The bot only collects data that is freely and publicly
  accessible. It does not bypass logins, paywalls, or anti-bot defenses.
- **Best-effort enrichment.** Many small business websites don't publish an
  email / phone. The scoring system reflects lead quality accordingly.
- **OSM coverage varies** by region. Dense urban areas have more data than
  rural ones. The adapter layer is designed so additional sources can be
  plugged in.
- **Rate-limited on purpose.** Concurrency, per-domain delays, and request
  timeouts are intentionally conservative to be polite to source servers.
- **No CAPTCHA bypass.** Sites that challenge automated access are skipped.

---

## Compliance notes

- Respect each source's Terms of Service. Nominatim and Overpass have
  [usage policies](https://operations.osmfoundation.org/policies/nominatim/).
  Set `CONTACT_EMAIL` in `.env` so your User-Agent identifies itself.
- Respect `robots.txt` (the enricher defaults to polite behavior).
- Do not use the bot to collect personal data about private individuals.
- Be aware of privacy laws (GDPR, CCPA, etc.) when storing or processing any
  contact information you scrape.

---

## Future improvements

- Pluggable LLM parser (already wired via an interface).
- Additional source adapters (public directories, industry registries).
- Job history & resume via the SQLite `jobs` table.
- FastAPI dashboard for browsing stored leads.
- Per-user quotas and job queueing.
- Webhook mode for Telegram (currently uses long polling).
- Redis-backed cache for multi-worker deployments.

---

## License

MIT (see repository root or add your own).
