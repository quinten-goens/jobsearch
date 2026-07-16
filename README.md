# Brussels job search

Finds live Brussels EU-affairs jobs and puts them in one filterable place.

Built around Sarah's target list of 282 organisations
(`conv/Sarah_Pernet_Brussels_Job_Search.xlsx`). The workbook is only ever read —
it stays her manual tracker, and nothing here writes to it.

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
.venv/bin/python -m jobsearch.orgs        # xlsx        -> data/orgs.json
.venv/bin/python -m jobsearch.discover    # find careers pages -> data/discovered.json
.venv/bin/python -m jobsearch.pipeline    # scrape everything  -> data/jobs.json
.venv/bin/streamlit run app.py            # browse it
```

`--boards` skips the per-org scrape and just hits the job boards; it takes
seconds and gives you most of the value. `--limit N` caps the org sweep.

Discovery is resumable: it saves after every organisation and keeps whatever
already resolved, so an interrupted run costs at most one org.

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
  pipeline.py   drives it all -> jobs.json
app.py          Streamlit UI
```
