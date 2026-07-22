"""Streamlit UI for the Brussels job search.

    streamlit run app.py

Organisations are the product: the question this answers is "where could I
work, and is it worth approaching them?" -- so the catalogue leads, jobs are a
supporting tab, and every organisation carries the context needed to judge it.
"""
import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

from jobsearch.config import JOBS_JSON
from jobsearch import store

st.set_page_config(page_title="Brussels job search", page_icon="🇧🇪", layout="wide")

# Categorical slots 1-3 from the validated reference palette; only a few are
# needed, which keeps colour alone safe to read.
SERIES = ["#2a78d6", "#008300", "#e87ba4"]


# PocketBase is the source of truth. Cache briefly so a rerun isn't a network
# round-trip, but short enough that a check or refresh shows up promptly.
@st.cache_data(ttl=60)
def load_catalogue() -> pd.DataFrame:
    try:
        rows = store.load_catalogue()
    except Exception as e:
        st.error(f"Could not reach PocketBase: {e}")
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("organisation", "sector", "category", "type", "base",
                "languages", "description", "why_fits", "target_roles",
                "careers_url", "careers_confidence", "homepage",
                "last_updated", "last_updated_trust", "search_url",
                "version_id", "last_check_verdict", "last_check_at", "id"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")
    if "sources" not in df:
        df["sources"] = [[] for _ in range(len(df))]
    for col, default in (("phd_relevant", False), ("latam_relevant", False),
                         ("remote_friendly", False), ("reviewed", False),
                         ("priority", None), ("size", None),
                         ("last_updated_age_days", None)):
        if col not in df:
            df[col] = default
    df["reviewed"] = df["reviewed"].fillna(False).astype(bool)
    for col in ("reviewed_url", "reviewed_page_date", "reviewed_at",
                "current_page_date"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")
    if "careers_score" not in df:
        df["careers_score"] = 0
    df["careers_score"] = (
        pd.to_numeric(df["careers_score"], errors="coerce").fillna(0).astype(int)
    )
    if "careers_reasons" not in df:
        df["careers_reasons"] = [[] for _ in range(len(df))]
    if "openings_state" not in df:
        df["openings_state"] = ""
    df["openings_state"] = df["openings_state"].fillna("")
    if "openings_count" not in df:
        df["openings_count"] = 0
    df["openings_count"] = (
        pd.to_numeric(df["openings_count"], errors="coerce").fillna(0).astype(int)
    )
    if "openings_titles" not in df:
        df["openings_titles"] = [[] for _ in range(len(df))]
    if "openings_new_titles" not in df:
        df["openings_new_titles"] = [[] for _ in range(len(df))]
    if "openings_new_at" not in df:
        df["openings_new_at"] = ""
    df["openings_new_at"] = df["openings_new_at"].fillna("")
    df["has_new"] = df["openings_new_titles"].apply(lambda x: bool(x))

    # Fit is scored at load time from the stored titles, so re-tuning the
    # profile never needs a re-scan. Cheap: a keyword scan per title.
    from jobsearch.fit import score_openings

    fit = df["openings_titles"].apply(lambda ts: score_openings(ts or []))
    df["fit_score"] = fit.apply(lambda x: x["best_score"])
    df["fit_band"] = fit.apply(lambda x: x["best_band"])
    df["fit_best_title"] = fit.apply(lambda x: x["best_title"])
    df["fit_strong"] = fit.apply(lambda x: x["strong"])
    df["has_careers"] = df["careers_url"].astype(bool)
    return df


@st.cache_data(ttl=120)
def load_jobs() -> tuple[pd.DataFrame, str]:
    if not JOBS_JSON.exists():
        return pd.DataFrame(), ""
    payload = json.loads(JOBS_JSON.read_text())
    df = pd.DataFrame(payload.get("jobs", []))
    if df.empty:
        return df, payload.get("generated_at", "")
    for col in ("title", "employer", "location", "source", "url",
                "posted", "deadline"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")
    df["posted_dt"] = pd.to_datetime(df["posted"], errors="coerce")
    df["deadline_dt"] = pd.to_datetime(df["deadline"], errors="coerce")
    today = pd.Timestamp(date.today())
    df["days_left"] = (df["deadline_dt"] - today).dt.days
    df["age_days"] = (today - df["posted_dt"]).dt.days
    return df, payload.get("generated_at", "")


def org_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Shared filter controls, rendered in the sidebar."""
    st.sidebar.subheader("Filter")
    q = st.sidebar.text_input("Search", placeholder="name, description, role…")
    sectors = st.sidebar.multiselect("Sector", sorted(df["sector"].unique()))

    # One-click "see everything": bypasses the recency filter entirely. Most of
    # the catalogue is hidden by default because we can't date the page, so give
    # a single obvious escape hatch rather than making people find two controls.
    show_all = st.sidebar.checkbox(
        "Show all organisations", value=False,
        help="By default you only see pages we can prove changed recently, "
             "which hides most of the catalogue. Turn this on to see every "
             "organisation, including the ones with no readable update date.",
    )
    if show_all:
        updated_within, include_undated = "Any time", True
    else:
        updated_within = st.sidebar.selectbox(
            "Careers page updated",
            ["Today", "In the last 2 days", "In the last 3 days",
             "In the last 7 days", "In the last 30 days",
             "In the last 90 days", "In the last year", "Any time"],
            index=4,  # 30 days is the requested default
            help="Show organisations whose careers page has changed recently. "
                 "Many sites don't say when they last updated — the toggle "
                 "below decides whether to include those.",
        )
        include_undated = st.sidebar.checkbox(
            "Also show pages with no update date", value=False,
            help="Only about 1 in 5 sites tells us when its page last changed. "
                 "With this off, you only see pages we can prove are recent — "
                 "which hides most communes and NGOs. Turn it on to see them too.",
        )

    st.sidebar.caption("Progress")
    reviewed = st.sidebar.radio(
        "Reviewed", ["All", "Not yet reviewed", "Reviewed"],
        label_visibility="collapsed",
        help="'Reviewed' means you've looked at that organisation's careers "
             "page. A refresh un-ticks it if the page has changed since.",
    )

    st.sidebar.caption("Openings")
    openings_choice = st.sidebar.radio(
        "Openings", ["Any", "Has openings now", "Hide 'no openings'"],
        label_visibility="collapsed",
        help="Whether the careers page has live openings right now. 'Has "
             "openings now' is the fast way to the organisations actually "
             "hiring on their own site — the ones worth applying to before the "
             "job boards fill up.",
    )
    good_fit_only = st.sidebar.checkbox(
        "Only openings that fit me", value=False,
        help="Show only organisations whose current openings match Sarah's "
             "profile — policy / international relations, Latin America / "
             "Spanish, or research / PhD, at the right level (not senior).",
    )

    st.sidebar.caption("Careers page link")
    link_choice = st.sidebar.radio(
        "How sure are we the link is right?",
        ["Any", "Only links we're sure about", "Hide guessed / missing links"],
        help="Some links we found and double-checked; others are a best guess, "
             "and a few we couldn't find at all. This lets you focus on the "
             "ones we're confident point to the real careers page.",
    )

    f = df
    if q:
        blob = (f["organisation"] + " " + f["description"] + " " +
                f["target_roles"] + " " + f["type"])
        f = f[blob.str.contains(q, case=False, na=False)]
    if sectors:
        f = f[f["sector"].isin(sectors)]
    if reviewed == "Reviewed":
        f = f[f["reviewed"]]
    elif reviewed == "Not yet reviewed":
        f = f[~f["reviewed"]]
    if updated_within != "Any time":
        days = {"Today": 0, "In the last 2 days": 2, "In the last 3 days": 3,
                "In the last 7 days": 7, "In the last 30 days": 30,
                "In the last 90 days": 90, "In the last year": 365}[updated_within]
        cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=days)
        dt = pd.to_datetime(f["last_updated"], errors="coerce")
        fresh_enough = dt >= cutoff
        # Pages with no parseable date are kept or dropped per the toggle.
        if include_undated:
            fresh_enough = fresh_enough | dt.isna()
        f = f[fresh_enough]
    if openings_choice == "Has openings now":
        f = f[f["openings_state"] == "has_openings"]
    elif openings_choice == "Hide 'no openings'":
        f = f[f["openings_state"] != "no_openings"]
    if good_fit_only:
        # A strong or possible match among the org's current openings.
        f = f[f["fit_band"].isin(["strong", "possible"])]
    conf = f["careers_confidence"].replace("", "none")
    if link_choice == "Only links we're sure about":
        f = f[conf == "high"]
    elif link_choice == "Hide guessed / missing links":
        f = f[conf.isin(["high", "medium"])]
    return f


# ------------------------------------------------------------ organisations
def page_organisations():
    st.title("Organisations")
    cat = load_catalogue()
    if cat.empty:
        st.warning("No catalogue yet — run `python -m jobsearch.catalogue`.")
        st.stop()
    f = org_filters(cat)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Shown", len(f))
    k2.metric("Hiring now", int((f["openings_state"] == "has_openings").sum()),
              help="Organisations with live openings on their own careers page.")
    fits = f[(f["openings_state"] == "has_openings")
             & f["fit_band"].isin(["strong", "possible"])]
    k3.metric("Hiring + fits you", len(fits),
              help="Hiring now AND at least one opening matches Sarah's "
                   "profile. Her best next actions.")
    k4.metric("Reviewed", int(f["reviewed"].sum()))

    if f.empty:
        st.info("No organisations match these filters.")
        st.stop()

    ref_col, dl_col = st.columns([3, 1])
    with ref_col:
        st.caption(
            "Tick **Reviewed** once you've looked at a careers page. "
            "**Refresh** re-checks the page — if it's changed since you "
            "reviewed it, the tick clears itself."
        )
    with dl_col:
        do_refresh = st.button(
            f"🔄 Refresh these {len(f)}", use_container_width=True,
            disabled=len(f) > 2500,
            help="Re-check every organisation shown (≤2500). Larger sweeps: "
                 "python -m jobsearch.enrich.",
        )

    if do_refresh:
        prog = st.progress(0.0, "Refreshing…")
        changed = uncheck = 0
        rows = f.to_dict("records")
        for i, rr in enumerate(rows, 1):
            try:
                res = store.refresh_org(rr)
                changed += bool(res.get("changed"))
                uncheck += bool(res.get("unreviewed"))
            except Exception:
                pass
            prog.progress(i / len(rows), f"{i}/{len(rows)}…")
        load_catalogue.clear()
        st.success(f"Refreshed {len(rows)} — {changed} URLs changed, "
                   f"{uncheck} un-reviewed (page updated).")
        st.rerun()

    # Best next actions first: hiring AND fits her, ranked by fit score; then
    # other hiring orgs; then the rest. Unreviewed above reviewed within a tier.
    view = f.copy()
    view["_hiring"] = (view["openings_state"] == "has_openings").astype(int)
    view["_fit_here"] = (view["_hiring"]
                         * view["fit_band"].isin(["strong", "possible"]).astype(int))
    view = view.sort_values(
        ["_fit_here", "_hiring", "fit_score", "reviewed", "organisation"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    # One editable table. Reviewed is a tickable checkbox; everything else is
    # read-only. Sarah works entirely here -- no detail panel, no button wall.
    # The org id rides along as a hidden column so we can map edits back.
    def _openings_label(state, count):
        if state == "has_openings":
            return f"🟢 {count} open" if count else "🟢 hiring"
        if state == "no_openings":
            return "— none now"
        return "?"  # unknown / not checked

    FIT_TAG = {"strong": "★ ", "possible": "· ", "weak": "", "none": "",
               "unknown": ""}
    best_opening = [
        (FIT_TAG.get(b, "") + t) if t else ""
        for b, t in zip(view["fit_band"], view["fit_best_title"])
    ]
    # Trimmed to the essentials Sarah acts on day-to-day. The dropped fields
    # (location, languages, page-date, link-quality) are still in the sidebar
    # filters and the CSV download.
    table = pd.DataFrame({
        "Reviewed": view["reviewed"].tolist(),
        "Organisation": view["organisation"].tolist(),
        "Openings": [_openings_label(s, c) for s, c in
                     zip(view["openings_state"], view["openings_count"])],
        "Best-matched opening": best_opening,
        "Sector": view["sector"].tolist(),
        "Careers page": view["careers_url"].tolist(),
        "Search instead": view["search_url"].tolist(),
        "_id": view["id"].tolist(),
    })

    edited = st.data_editor(
        table, hide_index=True, use_container_width=True, height=560,
        disabled=[c for c in table.columns if c != "Reviewed"],
        column_order=[c for c in table.columns if c != "_id"],
        column_config={
            "Reviewed": st.column_config.CheckboxColumn(
                "Reviewed", width="small",
                help="Tick once you've looked at this organisation's careers "
                     "page.",
            ),
            "Organisation": st.column_config.TextColumn(width="large"),
            "Openings": st.column_config.TextColumn(
                width="small",
                help="🟢 = live openings on their own careers page right now. "
                     "'— none now' = page says nothing open. '?' = we couldn't "
                     "read it (often a JavaScript site — worth a manual look)."),
            "Best-matched opening": st.column_config.TextColumn(
                width="large",
                help="The current opening that best fits Sarah's profile. "
                     "★ = strong fit, · = possible fit."),
            "Sector": st.column_config.TextColumn(width="medium"),
            "Careers page": st.column_config.LinkColumn(
                "Careers page", display_text="Open ↗", width="small",
                help="The page where this organisation lists its jobs."),
            "Search instead": st.column_config.LinkColumn(
                "Search instead", display_text="Search ↗", width="small",
                help="A Google search for their jobs — use this when we "
                     "couldn't find the page, or the link looks wrong."),
        },
        key="org_editor",
    )

    # Persist any ticked/unticked rows. Compare the editor's Reviewed column
    # against what we loaded, and write only the diffs to PocketBase.
    by_id = view.set_index("id")
    changed_rows = edited[edited["Reviewed"] != table["Reviewed"]]
    if not changed_rows.empty:
        for _, erow in changed_rows.iterrows():
            org_id = erow["_id"]
            row = by_id.loc[org_id]
            try:
                store.set_reviewed(
                    org_id, bool(erow["Reviewed"]),
                    current_url=row["careers_url"],
                    page_date=row["current_page_date"],
                )
            except Exception as e:
                st.error(f"Could not save review state: {e}")
        load_catalogue.clear()
        st.rerun()

    st.download_button(
        "Download as CSV", view.to_csv(index=False).encode(),
        file_name="brussels_organisations.csv", mime="text/csv",
    )

# ------------------------------------------------------------------ sectors
def page_sectors():
    cat = load_catalogue()
    st.title("Sectors")
    st.caption(f"How the {len(cat)} organisations break down, and how well "
               "each sector is covered.")

    by_sector = cat["sector"].value_counts()
    # Magnitude comparison: bars in one hue, horizontal for long names.
    st.subheader("Organisations per sector")
    st.bar_chart(by_sector, color=SERIES[0], horizontal=True, height=380)

    st.subheader("Careers-page coverage by sector")
    cov = (
        cat.groupby("sector")
        .agg(total=("organisation", "size"), found=("has_careers", "sum"))
        .assign(pct=lambda d: (d["found"] / d["total"] * 100).round(0))
        .sort_values("total", ascending=False)
    )
    st.dataframe(
        cov.reset_index().rename(columns={
            "sector": "Sector", "total": "Organisations",
            "found": "With careers page", "pct": "%",
        }),
        hide_index=True, use_container_width=True,
        column_config={"%": st.column_config.ProgressColumn(
            "%", format="%d%%", min_value=0, max_value=100
        )},
    )

    st.subheader("Where the organisations are")
    top_base = cat["base"].replace("", pd.NA).dropna().value_counts().head(12)
    st.bar_chart(top_base, color=SERIES[0], horizontal=True, height=320)

# --------------------------------------------------------------------- jobs
def page_jobs():
    st.title("Jobs")
    jobs, generated_at = load_jobs()
    if jobs.empty:
        st.info("No jobs scraped yet — run `python -m jobsearch.pipeline --boards`.")
        st.stop()

    when = ""
    if generated_at:
        try:
            when = datetime.fromisoformat(generated_at).strftime("%d %b %Y, %H:%M")
        except ValueError:
            when = generated_at
    st.caption(f"{len(jobs)} postings · last scraped {when}")

    c1, c2, c3 = st.columns([2, 1.3, 1.3])
    with c1:
        q = st.text_input("Search title or employer", placeholder="e.g. policy officer")
    with c2:
        srcs = st.multiselect("Source", sorted(jobs["source"].unique()))
    with c3:
        fresh = st.selectbox("Posted", ["Any time", "Last 7 days", "Last 30 days"])

    f = jobs
    if q:
        f = f[f["title"].str.contains(q, case=False, na=False)
              | f["employer"].str.contains(q, case=False, na=False)]
    if srcs:
        f = f[f["source"].isin(srcs)]
    if fresh != "Any time":
        days = 7 if "7" in fresh else 30
        f = f[f["age_days"].le(days) | f["age_days"].isna()]
    f = f[f["days_left"].isna() | f["days_left"].ge(0)]

    k1, k2, k3 = st.columns(3)
    k1.metric("Open now", len(f))
    k2.metric("Posted this week", int(f["age_days"].le(7).sum()))
    k3.metric("Closing within 7 days",
              int((f["days_left"].le(7) & f["days_left"].ge(0)).sum()))
    st.divider()

    view = f.sort_values("posted_dt", ascending=False, na_position="last")
    st.dataframe(
        pd.DataFrame({
            "Title": view["title"],
            "Employer": view["employer"].replace("", "—"),
            "Location": view["location"].replace("", "—"),
            "Posted": view["posted_dt"].dt.strftime("%d %b").fillna("—"),
            "Deadline": view["deadline_dt"].dt.strftime("%d %b").fillna("—"),
            "Left": view["days_left"],
            "Link": view["url"],
        }),
        hide_index=True, use_container_width=True, height=520,
        column_config={
            "Title": st.column_config.TextColumn(width="large"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open ↗",
                                                width="small"),
            "Left": st.column_config.NumberColumn("Left", format="%dd"),
        },
    )

# ----------------------------------------------------------------- coverage
def page_coverage():
    cat = load_catalogue()
    st.title("Coverage")
    st.caption("How the catalogue was built and where it's weak — so you know "
               "what to trust.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Organisations", len(cat))
    k2.metric("Careers page found", int(cat["has_careers"].sum()))
    k3.metric("High confidence", int((cat["careers_confidence"] == "high").sum()))
    k4.metric("With an update date", int(cat["last_updated"].astype(bool).sum()))

    st.divider()
    st.subheader("Where each organisation came from")
    src = cat.explode("sources")["sources"].dropna().value_counts()
    st.bar_chart(src, color=SERIES[0], horizontal=True, height=280)

    st.subheader("Stale careers pages")
    st.caption(
        "Pages that haven't changed in a long time are less likely to be worth "
        "checking. Only pages that publish a trustworthy date appear here — an "
        "HTTP header on a dynamic page is usually just render time, so those "
        "are excluded rather than treated as evidence."
    )
    stale = cat[
        cat["last_updated_trust"].isin(["high", "medium"])
        & cat["last_updated_age_days"].notna()
    ].copy()
    if stale.empty:
        st.info("No organisations with a trustworthy update date yet.")
    else:
        stale = stale.sort_values("last_updated_age_days", ascending=False)
        st.dataframe(
            pd.DataFrame({
                "Organisation": stale["organisation"],
                "Sector": stale["sector"],
                "Last updated": stale["last_updated"],
                "Days ago": stale["last_updated_age_days"],
                "Careers page": stale["careers_url"],
            }).head(40),
            hide_index=True, use_container_width=True,
            column_config={
                "Careers page": st.column_config.LinkColumn(display_text="Open ↗"),
                "Days ago": st.column_config.NumberColumn(format="%d"),
            },
        )

    st.subheader("Organisations with no careers page found")
    missing = cat[~cat["has_careers"]]
    st.caption(f"{len(missing)} organisations. Each keeps a search link rather "
               "than a guessed URL.")
    if not missing.empty:
        st.dataframe(
            pd.DataFrame({
                "Organisation": missing["organisation"],
                "Sector": missing["sector"],
                "Search": missing["search_url"],
            }),
            hide_index=True, use_container_width=True, height=240,
            column_config={"Search": st.column_config.LinkColumn(
                display_text="Search ↗"
            )},
        )


# ----------------------------------------------------------------- what's new
def page_whats_new():
    st.title("What's new")
    st.caption("Openings that appeared since the last time each organisation "
               "was checked — the off-board jobs, seen early, before the boards "
               "fill up. Best-fitting first.")
    cat = load_catalogue()
    new = cat[cat["has_new"]].copy()
    if new.empty:
        st.info("Nothing new since the last scan. Hit **Refresh** on the "
                "Organisations page (or re-run discovery) to check again.")
        st.stop()

    # Rank by fit of the newly-appeared titles.
    from jobsearch.fit import score_openings
    new["_newfit"] = new["openings_new_titles"].apply(
        lambda ts: score_openings(ts or [])["best_score"])
    new = new.sort_values("_newfit", ascending=False)

    st.metric("Organisations with new openings", len(new))
    if st.button("Mark all as seen"):
        for _, r in new.iterrows():
            if r["version_id"]:
                try:
                    store.clear_new_openings(r["version_id"])
                except Exception:
                    pass
        load_catalogue.clear()
        st.rerun()

    for _, r in new.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{r['organisation']}** · {r['sector']}"
                            + (f" · {r['base']}" if r['base'] else ""))
                for t in r["openings_new_titles"]:
                    fit = score_openings([t])["scored"][0]
                    tag = ("★" if fit["band"] == "strong"
                           else "·" if fit["band"] == "possible" else " ")
                    st.markdown(f"&nbsp;&nbsp;{tag} 🆕 {t}", unsafe_allow_html=True)
            with c2:
                if r["careers_url"]:
                    st.link_button("Open ↗", r["careers_url"],
                                   use_container_width=True)
                if r["version_id"] and st.button(
                        "Seen", key=f"seen_{r['id']}", use_container_width=True):
                    try:
                        store.clear_new_openings(r["version_id"])
                        load_catalogue.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


# ----------------------------------------------------------------- navigation
# Proper Streamlit multipage nav (not a radio): each page is its own entry in
# the sidebar, with the browser URL and back/forward working per page.
#
# Streamlit renders the nav at the very top of the sidebar. To put the title
# *above* it, we pin the title with position:sticky and a negative margin via a
# tiny CSS shim, then declare the nav as a section so it reads as one unit.
st.markdown(
    """<style>
    [data-testid="stSidebarNav"]::before {
        content: "🇧🇪 Brussels job search";
        display: block;
        font-size: 1.25rem; font-weight: 700;
        padding: 0.5rem 1rem 0.75rem 0.75rem;
    }
    </style>""",
    unsafe_allow_html=True,
)
nav = st.navigation([
    st.Page(page_organisations, title="Organisations", icon="🏢", default=True),
    st.Page(page_whats_new, title="What's new", icon="🆕"),
    st.Page(page_sectors, title="Sectors", icon="📊"),
    st.Page(page_jobs, title="Jobs", icon="💼"),
    st.Page(page_coverage, title="Coverage", icon="🔍"),
])
nav.run()
