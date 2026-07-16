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
.venv/bin/streamlit run app.py             # browse it
```

Jobs (secondary):

```bash
.venv/bin/python -m jobsearch.pipeline --boards   # job boards only, seconds
.venv/bin/python -m jobsearch.pipeline           # + every org careers page, ~30 min
```

`enrich` only touches rows without a careers URL, so re-running it is cheap;
`--all` forces a redo. Both it and `discover` write after every organisation, so
an interrupted run costs at most the requests in flight.

## Is this careers page worth checking?

`freshness.py` answers that, and is careful about how much it claims. Four
sources, ranked by trust:

| Source | Trust | Why |
|---|---|---|
| CMS `dateModified` / `article:modified_time` | high | the site's own "content changed" stamp |
| sitemap `<lastmod>` | medium | usually maintained |
| `Last-Modified` header | **low** | on a dynamic page this is the render time, not a content change — left.eu reports "today" on every request |
| nothing published | none | most pages, in practice |

Only high/medium dates are treated as evidence, so a page is never called stale
on the strength of a missing header. It works: Protection International's
vacancies page was last touched 255 days ago (consistent with its "no vacancies
at this time"), and Braine-l'Alleud's is over four years old.

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
