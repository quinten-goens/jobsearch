# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Brussels EU-affairs job-search tool. Its purpose: surface a small number of openings genuinely worth applying to — especially **off-board** ones on organisations' own careers pages, before the saturated job boards fill up. The profile it scores against is fixed (policy / international relations, Latin America / Spanish angle, research / PhD, 2–5 years' experience).

## Commands

Always use the venv interpreter: `.venv/bin/python`.

```bash
# --- one-time / occasional (rebuild the catalogue, spends Brave quota) ---
.venv/bin/python -m jobsearch.catalogue   # merge sheet+registry+directories+register -> data/catalogue.json
.venv/bin/python -m jobsearch.enrich      # discover careers URL + freshness + openings for orgs missing a URL
.venv/bin/python -m jobsearch.enrich --all # re-discover EVERY org (uses Brave search quota — costly)

# --- the daily job (discovery-free, cheap, rate-limit-safe) ---
.venv/bin/python -m jobsearch.refresh            # re-check known pages, then sync to PocketBase
.venv/bin/python -m jobsearch.refresh --no-sync  # local only
.venv/bin/python -m jobsearch.refresh --limit 50 # first N orgs (smoke test)

# --- PocketBase ---
.venv/bin/python -m jobsearch.pb_schema          # create/repair collections (idempotent, self-healing)
.venv/bin/python -m jobsearch.pb_schema --show   # print collections + fields
.venv/bin/python -m jobsearch.pb_sync            # push data/catalogue.json -> PocketBase

# --- UI ---
.venv/bin/streamlit run app.py                   # reads live from PocketBase

# --- jobs board scrape (secondary; needs Chromium for JS pages) ---
.venv/bin/python -m jobsearch.pipeline --boards  # EuroBrussels/Euractiv only, fast, no browser
.venv/bin/python -m jobsearch.pipeline           # + per-org scrape, slow, uses Chromium
```

There is **no test suite**. Verify changes by running the relevant `-m` module against real data, or with small `unittest.mock.patch`-based checks of the pure functions (`freshness.last_updated`, `fit.score_title`, `openings.detect`, `discover.score_candidate`/`verify_page`) — that is the established pattern in this codebase for confirming logic.

Most modules have a `__main__` block for direct invocation, e.g. `.venv/bin/python -m jobsearch.openings <url>` and `.venv/bin/python -m jobsearch.fit "Policy Officer"`.

## Architecture

### The pipeline (offline compute → PocketBase → UI)

Heavy work writes `data/catalogue.json` locally; `pb_sync` pushes it to PocketBase; the app reads only from PocketBase. This decoupling exists because PocketHost caps requests at **1,000/hour** — so all PocketBase writes go through the **batch API** (`/api/batch`), turning a full sync into a handful of calls, not thousands.

```
sheet + registry.py + directories.py + register.py
        └─ catalogue.py (merge + dedup) ─────────────► data/catalogue.json
                                                              │
   enrich.py / refresh.py  (discover.py, freshness.py,        │ read+write
                            openings.py, fit.py)  ────────────┤
                                                              ▼
                                        pb_sync.py ──► PocketBase (source of truth)
                                                              ▲
                                                app.py, store.py (read/write)
```

**PocketBase is the single source of truth for the app.** `store.py` is the app's whole view of it: it flattens the relational rows back into the per-org dict the UI expects (`_flatten`), and holds the two user write-paths (mark reviewed, refresh an org). `enrich`/`refresh` are the only things that populate the catalogue; the app never runs discovery.

### PocketBase schema (jobsearch/pb_schema.py)

- **organisations** — stable identity + metadata. Superuser-write only (the catalogue can't be corrupted through the app). Has `current_url` → the live url_version, plus `reviewed`/`reviewed_url`/`reviewed_page_date`/`reviewed_at`.
- **url_versions** — every careers URL ever found for an org; `superseded=false` marks the current one. Carries the openings snapshot, freshness (`last_updated`, `last_updated_source`), `content_hash`, `page_text`, `openings_deadline`, and the `openings_new_*` "what's new" flags.
- **url_checks** — timestamped log of GUI actions.
- **app_settings** — a `key → JSON` store for user-tunable settings (e.g. `fit_dims`, the fit toggles).

`pb_schema.main()` is **idempotent and self-healing**: `_ensure_fields` adds any spec field a live collection is missing *and* reconciles a raised `max` on existing text fields. Run it after adding a field to a spec. **Gotcha:** PocketBase `text` fields cap at 5000 chars by default and use `max` (not `maxSize`) — set `max` explicitly for anything longer (e.g. `page_text`).

### Freshness & change detection (jobsearch/freshness.py) — the subtle core

`last_updated(url, prev_hash, prev_date)` answers "when did this page last change?" from, in order: CMS metadata date (high trust) → sitemap `<lastmod>` (medium) → **content-hash change** → `Last-Modified` header (low, usually just render time). The content hash is the load-bearing part:

- Only ~1/3 of careers pages publish a date. For the rest, we fingerprint the visible text (`_visible_text`, with volatile tokens like session ids/clocks stripped so a re-render doesn't look like a change) and date the page *by change*: a differing hash since the last scan means "updated now".
- **A detected hash change overrides even a metadata date** (a hand-edited NGO page often adds a vacancy without bumping `dateModified`). That override returns `source="hash"`, today, high trust.
- **Change detection needs the fingerprint stored on every scan of every page** so the next scan can compare. This is why `pb_sync` writes `content_hash` even on the unchanged-URL branch, and why a metadata-less unchanged page stays `hash-seeded` (never blanks) — both were real bugs that silently stalled detection. `source="hash"` (a real change) only appears from the **second** durable-baseline run onward.

### Discovery & scoring (jobsearch/discover.py)

`discover_one` resolves a careers URL by: `probe_homepage` (try `PROBE_PATHS` on the known domain first — zero Brave cost) → Brave/DDG search → `score_candidate` (URL/path/domain/geography signals) + `verify_page` (evidence on the fetched page). `THRESHOLD=10`. Key ideas encoded here:
- 403/401/429 = "site blocks scrapers" (all of europa.eu, Cloudflare) → **neutral (0), not dead** — penalising these sank real EU-institution pages.
- Path hints are multilingual regexes (NL/FR/EN/DE/ES) because Belgian sites decorate the words freely.
- `verify_page` penalises **membership / B2B "become a member" pages** (federations' "join us" pages score on the same words as careers pages) — but never when the URL/title already says careers.

### Openings & fit

- **openings.py** — HTML-only (no browser) detection of whether a page has live openings *right now*: JSON-LD `JobPosting`, job-shaped links, multilingual empty-state copy. Returns `state` (has/none/unknown), titles, and best-effort `deadline` (`validThrough` or a date near a deadline cue).
- **fit.py** — `score_title`/`score_openings` score an opening 0–100 against the profile, with human-readable reasons. Takes an optional `dims` dict to toggle scoring dimensions on/off (policy/latam/research/comms/seniority); the app persists Sarah's toggles in `app_settings` and applies them **live** via `app.apply_fit` (kept out of the cached loader so a toggle re-ranks without a re-scan).

### The app (app.py)

Streamlit multipage (`st.navigation`). Gated behind `APP_PWD` (`require_password`, before nav). `load_catalogue` is `@st.cache_data`; **fit is applied after the cache** so toggles re-rank live. The Organisations page is one editable `st.data_editor` table (only the Reviewed checkbox is writable). "What's new" surfaces new opening titles + hash-changed pages. Reviewed auto-unticks when a page changes after review (the reviewed snapshot in `set_reviewed` vs. the new page date in `refresh_org`).

## Conventions & constraints

- **Credentials** resolve via a layered accessor (`config._secret` / `pb._secret`): process env → `.env` file → Streamlit `st.secrets`, in that order, so the same code runs locally, in Docker/Dokploy (env vars), and on Streamlit Cloud (`st.secrets`). Never read `.env` directly. Env vars used: `PH_URL`, `PH_USR`, `PH_PWD`, `PH_ADMIN_USR`/`PH_ADMIN_PWD` (schema/organisation writes only), `BRAVE_KEY`, `APP_PWD`.
- **The xlsx is read-only** (`conv/Sarah_Pernet_Brussels_Job_Search.xlsx`) — it's the user's manual tracker; never write to it.
- **HTTP goes through `http.fetch`** (cached 24h under `data/cache/`) so re-runs are cheap and small NGO sites aren't hammered. Openings/freshness/page-text all reuse the same cached response — capturing extra data from a scan is nearly free.
- **Deployment**: the `Dockerfile` builds a runtime image that idles (`sleep infinity`); Dokploy runs `docker exec <container> python -m jobsearch.refresh` on a nightly cron. `/app/data` must be a persistent volume (the content-hash baseline lives there); `docker-entrypoint.sh` seeds `catalogue.json` from `/app/seed` on first boot only.
- `data/transparency_register.xml` (108 MB) is tracked via **Git LFS**.
- The GitHub remote reports "moved" to `github.com/quinten-goens/jobsearch.git`; pushes still work via redirect.
