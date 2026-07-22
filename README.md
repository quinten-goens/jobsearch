# Brussels job search

A documented catalogue of **413 organisations** in and around Brussels — who
they are, what they do, and where their careers page is — plus the live jobs
they're advertising.

Organisations are the point: the question is "where could I work, and is it
worth approaching them?" Jobs are a supporting view.

It started from Sarah's hand-built target list of 282
(`conv/Sarah_Pernet_Brussels_Job_Search.xlsx`, only ever read — it stays her
manual tracker) and extends it in two ways:

- **Where a sector has a knowable membership, enumerate it.** The sheet had 4 of
  the 19 Brussels communes. `registry.py` carries all 19, the 26-commune
  periphery, and Belgium's universities — each with size, working language and a
  note on what makes it distinct. Universities carry an anthropology flag, since
  the PhD route is a specific goal.
- **Where it doesn't, harvest it.** NGOs and grassroots groups have no
  authoritative list, so `directories.py` scrapes the federations that publish
  their membership (CNCD-11.11.11, ngo-federatie) rather than hand-curating a
  list that would just be guesswork.

Cross-cutting themes are flags rather than categories: **38 organisations are
anthropology/PhD-relevant**, **86 are Latin America / Spanish-relevant**.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium     # only needed for JS-rendered pages
```

Strongly recommended — a [Brave Search API](https://brave.com/search/api) key
(2,000 queries/month free, no card). Either name works:

```bash
echo 'BRAVE_KEY=your-key-here' > .env
```

It's the difference between a ~5-minute sweep and a multi-hour one. Without it,
discovery falls back to scraping DuckDuckGo, which **soft-bans after roughly 20
searches** and then returns empty results rather than an error — so it needs a
~15s delay per query to survive 282 organisations.

## Usage

```bash
.venv/bin/python -m jobsearch.orgs         # xlsx -> data/orgs.json
.venv/bin/python -m jobsearch.directories  # NGO federations -> directory_orgs.json
.venv/bin/python -m jobsearch.catalogue    # merge all three -> catalogue.json
.venv/bin/python -m jobsearch.enrich       # careers page + freshness per org
.venv/bin/python -m jobsearch.pb_schema    # create PocketBase collections (once)
.venv/bin/python -m jobsearch.pb_sync      # push catalogue.json -> PocketBase
.venv/bin/streamlit run app.py             # browse it (reads live from PocketBase)
```

## Storage: PocketBase

The app reads and writes a hosted PocketBase (PocketHost) instance, which is the
source of truth. Three collections:

- **organisations** — one row per org, stable identity + metadata.
- **url_versions** — every careers URL a discovery run has found. A refresh
  appends a new version and supersedes the old one; nothing is deleted, so the
  full history of how a URL changed is kept.
- **url_checks** — a timestamped log of what the user did in the GUI (marked a
  link good/wrong/dead, applied).

The heavy discovery work (`enrich`) still writes `catalogue.json` locally, and
`pb_sync` pushes it up. This keeps the slow compute decoupled from PocketHost's
**1,000-requests/hour limit** — everything to PocketBase goes through the batch
API, so a full 665-org sync is a handful of calls, not thousands.

Credentials live in `.env`: `PH_ADMIN_*` for schema creation, `PH_*` for the
app's day-to-day reads and writes.

## Daily refresh (Docker + Dokploy)

The catalogue is only useful if it stays current: a page that gained an opening
yesterday should surface today. `jobsearch.refresh` is the job that keeps it
fresh, and the `Dockerfile` packages the code to run it on a schedule.

```bash
.venv/bin/python -m jobsearch.refresh            # re-check every known page, then sync
.venv/bin/python -m jobsearch.refresh --no-sync  # local only
.venv/bin/python -m jobsearch.refresh --limit 50 # first 50 (smoke test)
```

What one run does, per org that already has a careers URL: re-checks freshness
(metadata date, else content-hash change detection) and re-scans live openings,
then `pb_sync` pushes the snapshot to PocketBase. It is **discovery-free** — it
never searches for new URLs (that's `enrich`, which spends Brave quota) — so
it's cheap and rate-limit-safe to run every day.

### The container is a runtime, not a cron

The image deliberately **does not run anything on start** — it holds the code
and dependencies and then idles (`sleep infinity`). You spin it up once with
Dokploy, and schedule the work separately so the container stays a stable,
ready-to-exec runtime:

```bash
docker exec <container> python -m jobsearch.refresh
```

In Dokploy: deploy this repo as an app (it builds the `Dockerfile`), then add a
**Scheduled Job** running that `docker exec` line once a day.

Two things the deployment needs:

- **`.env` injected at runtime**, not baked into the image (`.dockerignore`
  keeps it out). Set `PH_URL`, `PH_USR`, `PH_PWD`, `PH_ADMIN_USR`,
  `PH_ADMIN_PWD`, and `BRAVE_KEY` as Dokploy environment variables.
- **A volume mounted at `/app/data`.** The HTTP cache and, crucially, the
  content-hash freshness baseline live there. Without a persistent volume every
  run looks like a "first scan" and can't date the metadata-less pages by change
  (see below) — the whole point of running daily. In Dokploy: *Advanced →
  Volumes → Add Mount*, type **Volume**, mount path `/app/data`.

  The volume starts empty, but you don't need to seed it by hand: the image bakes
  a copy of `catalogue.json` at `/app/seed` (outside the volume, so the mount
  can't hide it), and `docker-entrypoint.sh` copies it into `/app/data` on the
  **first** boot only. Later boots keep the live catalogue that `refresh` has been
  updating in place. To ship a fresh catalogue, rebuild the image (it re-bakes the
  current `data/catalogue.json`) and clear the volume, or just `docker cp` a new
  one in.

The base image is browser-free (the daily refresh is HTTP-only). If you also run
the job-board scrape (`jobsearch.pipeline`) in-container, add
`RUN playwright install --with-deps chromium` to the `Dockerfile`.

Jobs (secondary):

```bash
.venv/bin/python -m jobsearch.pipeline --boards   # job boards only, seconds
.venv/bin/python -m jobsearch.pipeline           # + every org careers page, ~30 min
```

`enrich` only touches rows without a careers URL, so re-running it is cheap;
`--all` forces a redo. Both it and `discover` write after every organisation, so
an interrupted run costs at most the requests in flight.

## Is this careers page worth checking?

`freshness.py` answers that, and is careful about how much it claims. Sources,
ranked by trust:

| Source | Trust | Why |
|---|---|---|
| CMS `dateModified` / `article:modified_time` | high | the site's own "content changed" stamp |
| sitemap `<lastmod>` | medium | usually maintained |
| **content-hash change** | medium | *we* date the page: a changed fingerprint since the last scan means "updated now" |
| `Last-Modified` header | **low** | on a dynamic page this is the render time, not a content change — left.eu reports "today" on every request |
| nothing published | none | only on a page's very first scan |

Only high/medium dates are treated as evidence, so a page is never called stale
on the strength of a missing header. It works: Protection International's
vacancies page was last touched 255 days ago (consistent with its "no vacancies
at this time"), and Braine-l'Alleud's is over four years old.

**Dating the pages that publish no date.** Only about a third of careers pages
expose any last-updated metadata, so the rest used to be undateable and hidden
by default. The fix: fingerprint each page's meaningful text (site chrome and
volatile tokens — clocks, session ids, CSRF nonces — stripped first), store it,
and on the next run compare. A changed hash *is* the "this page was updated"
event, on a date we control, for every readable page. It only bites from the
**second** scan onward — the first has no baseline to diff against — which is
why the daily refresh and its persistent `/app/data` volume matter.

## How it finds careers pages

The old sheet's links were half guesswork, and the guesses failed in exactly the
way you'd expect: Protection International's page was `/vacancies/`, not the
`/jobs/` that had been assumed.

So `discover.py` doesn't guess paths. For each organisation it runs a few search
queries, fetches the top candidates, and scores each one on evidence:

- **Path shape** — does the URL look like a careers page, in EN/FR/NL/ES?
- **Domain ownership** — does the domain match the org's name or acronym?
- **Geography** — a Brussels job search shouldn't land on the Belgian embassy in
  Washington. Foreign-office pages are real pages for the wrong city and score
  identically on every other signal, so they're penalised explicitly.
- **Known domain** — the old sheet's *paths* were unreliable but its *domains*
  usually weren't, and they disambiguate names that collide across countries.
- **Page evidence** — does the fetched page actually contain job-listing
  language?

Every result carries its score and the reasons behind it, so a wrong pick is
debuggable rather than mysterious. Anything below the threshold is reported as
`none` rather than guessed at, and each org keeps a Google-search fallback link.

## How it scrapes

There is no single scraper that works across 282 bespoke websites, so
`scrape.py` is layered by descending reliability, and each job records which
layer found it:

| Method | Reliability |
|---|---|
| `ats:*` — Greenhouse/Lever/Recruitee JSON APIs | exact |
| `jsonld` — schema.org `JobPosting` | exact |
| `board` — hand-written adapters for EuroBrussels and Euractiv | high |
| `generic` / `rendered:*` — heuristics over static or browser-rendered HTML | best-effort |

Two things worth knowing:

**The boards carry most of the value.** EuroBrussels and Euractiv aggregate live
Brussels policy jobs from these same organisations in clean HTML. Five adapters
beat 282 scrapers.

**An empty careers page is normal, not a bug.** Small NGOs post a job every few
months. The scraper distinguishes "this page says it has no openings"
(`empty-page`) from "we found nothing and don't know why" (`no-jobs-found`), so
you can tell a quiet org from a broken scrape.

## Known limits

- **Euractiv publishes no employer name** anywhere machine-readable — not on the
  card, detail page, JSON-LD, or meta tags. Those rows show `—` rather than a
  guess.
- **jobsin.brussels** is a Nuxt app that loads listings after hydration; it
  resisted headless rendering and is not included.
- **DuckDuckGo bans on volume.** See Setup.
- Some careers pages are Vue/React apps invisible to plain HTTP. Those get
  retried through Chromium automatically, which is slow (seconds per page), so
  it only happens when the cheap path finds nothing.

## Layout

```
jobsearch/
  config.py     paths, HTTP headers, API key
  http.py       cached fetching (24h)
  search.py     Brave API -> DuckDuckGo fallback, cached a week
  orgs.py       xlsx -> orgs.json
  discover.py   search + score -> careers page per org
  scrape.py     layered extraction + date parsing
  boards.py     EuroBrussels, Euractiv
  render.py     headless Chromium for JS pages
  freshness.py  when a page last changed (metadata, else content-hash)
  openings.py   does a page have live openings right now? (HTML only)
  enrich.py     careers page + freshness + openings per org
  refresh.py    daily re-check of known pages, then sync (Docker entrypoint)
  pb_sync.py    push catalogue.json -> PocketBase (batch API)
  store.py      the app's read/write view of PocketBase
  pipeline.py   drives the job-board scrape -> jobs.json
app.py          Streamlit UI
Dockerfile      runtime image for the scheduled daily refresh
```
