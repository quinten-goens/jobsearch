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
from jobsearch.discover import HIGH_THRESHOLD, THRESHOLD
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


cat = load_catalogue()
if cat.empty:
    st.warning("No catalogue yet — run `python -m jobsearch.catalogue`.")
    st.stop()

# ------------------------------------------------------------------ sidebar
st.sidebar.title("🇧🇪 Brussels job search")
page = st.sidebar.radio(
    "View",
    ["Organisations", "Sectors", "Jobs", "Coverage"],
    label_visibility="collapsed",
)
st.sidebar.divider()

st.sidebar.caption(f"{len(cat)} organisations · {int(cat['has_careers'].sum())} "
                   "with a careers page")


def org_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Shared filter controls, rendered in the sidebar."""
    st.sidebar.subheader("Filter")
    q = st.sidebar.text_input("Search", placeholder="name, description, role…")
    sectors = st.sidebar.multiselect("Sector", sorted(df["sector"].unique()))
    bases = st.sidebar.multiselect("Based in", sorted(
        b for b in df["base"].unique() if b
    ))
    langs = st.sidebar.multiselect(
        "Working language", ["FR", "NL", "EN", "ES"]
    )
    st.sidebar.caption("Themes")
    phd = st.sidebar.checkbox("Anthropology / PhD route")
    latam = st.sidebar.checkbox("Latin America / Spanish")
    remote = st.sidebar.checkbox("Hires remote / worldwide")

    st.sidebar.caption("Progress")
    reviewed = st.sidebar.radio(
        "Reviewed", ["All", "Not yet reviewed", "Reviewed"],
        label_visibility="collapsed",
        help="'Reviewed' means you've checked the current careers page. A "
             "refresh un-ticks it if the page has been updated since.",
    )

    st.sidebar.caption("Page freshness")
    updated_within = st.sidebar.selectbox(
        "Updated within",
        ["Last 30 days", "Last 90 days", "Last year", "Any time"],
        index=0,  # 30 days is the requested default
        help="Filters on the careers page's last-updated date. Only ~1/3 of "
             "pages publish a trustworthy date; use the toggle below to decide "
             "what to do with the rest.",
    )
    include_undated = st.sidebar.checkbox(
        "Also show pages with no known date", value=False,
        help="Only ~1 in 5 pages publishes a trustworthy update date. With "
             "this off, the freshness filter is strict but hides every page "
             "that doesn't advertise its age (most communes and NGOs). Turn "
             "it on to keep those too.",
    )

    st.sidebar.caption("Careers page")
    conf = st.sidebar.multiselect(
        "Confidence", ["high", "medium", "none"],
        help="How sure the scorer is that this really is the org's careers page",
    )
    lo, hi = int(df["careers_score"].min()), int(df["careers_score"].max())
    min_score = st.sidebar.slider(
        "Minimum score", lo, hi, lo,
        help=(
            "The scorer's evidence total: careers-shaped path, domain "
            f"ownership, geography and page content. ≥{HIGH_THRESHOLD} is "
            f"high confidence, ≥{THRESHOLD} is medium; below that we report "
            "no page rather than guess."
        ),
    )

    f = df
    if q:
        blob = (f["organisation"] + " " + f["description"] + " " +
                f["target_roles"] + " " + f["type"])
        f = f[blob.str.contains(q, case=False, na=False)]
    if sectors:
        f = f[f["sector"].isin(sectors)]
    if bases:
        f = f[f["base"].isin(bases)]
    if langs:
        f = f[f["languages"].str.contains("|".join(langs), case=False, na=False)]
    if phd:
        f = f[f["phd_relevant"]]
    if latam:
        f = f[f["latam_relevant"]]
    if remote:
        f = f[f["remote_friendly"]]
    if reviewed == "Reviewed":
        f = f[f["reviewed"]]
    elif reviewed == "Not yet reviewed":
        f = f[~f["reviewed"]]
    if updated_within != "Any time":
        days = {"Last 30 days": 30, "Last 90 days": 90, "Last year": 365}[updated_within]
        cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=days)
        dt = pd.to_datetime(f["last_updated"], errors="coerce")
        fresh_enough = dt >= cutoff
        # Pages with no parseable date are kept or dropped per the toggle.
        if include_undated:
            fresh_enough = fresh_enough | dt.isna()
        f = f[fresh_enough]
    if conf:
        f = f[f["careers_confidence"].replace("", "none").isin(conf)]
    if min_score > lo:
        f = f[f["careers_score"] >= min_score]
    return f


# ------------------------------------------------------------ organisations
if page == "Organisations":
    st.title("Organisations")
    f = org_filters(cat)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Shown", len(f))
    k2.metric("With careers page", int(f["has_careers"].sum()))
    k3.metric("Reviewed", int(f["reviewed"].sum()))
    k4.metric("Anthropology / PhD", int(f["phd_relevant"].sum()))
    k5.metric("Latin America", int(f["latam_relevant"].sum()))

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
            disabled=len(f) > 60,
            help="Re-check every organisation shown (≤60). Larger sweeps: "
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

    view = f.sort_values(["reviewed", "sector", "organisation"]).reset_index(drop=True)
    # One editable table. Reviewed is a tickable checkbox; everything else is
    # read-only. Sarah works entirely here -- no detail panel, no button wall.
    # The org id rides along as a hidden column so we can map edits back.
    table = pd.DataFrame({
        "Reviewed": view["reviewed"].tolist(),
        "Organisation": view["organisation"].tolist(),
        "Sector": view["sector"].tolist(),
        "Based in": view["base"].tolist(),
        "Lang": view["languages"].tolist(),
        "Updated": view["last_updated"].replace("", "—").tolist(),
        "Score": view["careers_score"].tolist(),
        "Careers page": view["careers_url"].tolist(),
        "Fallback search": view["search_url"].tolist(),
        "_id": view["id"].tolist(),
    })

    edited = st.data_editor(
        table, hide_index=True, use_container_width=True, height=560,
        disabled=[c for c in table.columns if c != "Reviewed"],
        column_order=[c for c in table.columns if c != "_id"],
        column_config={
            "Reviewed": st.column_config.CheckboxColumn(
                "✓", width="small",
                help="Tick once you've reviewed this careers page.",
            ),
            "Organisation": st.column_config.TextColumn(width="large"),
            "Sector": st.column_config.TextColumn(width="medium"),
            "Based in": st.column_config.TextColumn(width="small"),
            "Careers page": st.column_config.LinkColumn(
                display_text="Open ↗", width="small"),
            "Fallback search": st.column_config.LinkColumn(
                display_text="Search ↗", width="small"),
            "Updated": st.column_config.TextColumn(
                width="small", help="When the careers page last changed"),
            "Score": st.column_config.NumberColumn(
                width="small", format="%d",
                help=f"Evidence total. ≥{HIGH_THRESHOLD} high, ≥{THRESHOLD} medium."),
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
elif page == "Sectors":
    st.title("Sectors")
    st.caption("How the 413 organisations break down, and how well each sector "
               "is covered.")

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
elif page == "Jobs":
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
else:
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
