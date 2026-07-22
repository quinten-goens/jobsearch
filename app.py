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
MUTED = "#898781"

CONF_ICON = {"high": "🟢", "medium": "🟡", "none": "⚪", "": "⚪"}
TRUST_NOTE = {
    "high": "the site's own 'content changed' stamp",
    "medium": "the site's sitemap",
    "low": "an HTTP header — on a dynamic page this is often just render time",
    "none": "no date published",
}


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
                         ("remote_friendly", False),
                         ("priority", None), ("size", None),
                         ("last_updated_age_days", None)):
        if col not in df:
            df[col] = default
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
    if conf:
        f = f[f["careers_confidence"].replace("", "none").isin(conf)]
    if min_score > lo:
        f = f[f["careers_score"] >= min_score]
    return f


# ------------------------------------------------------------ organisations
if page == "Organisations":
    st.title("Organisations")
    f = org_filters(cat)
    st.caption(f"{len(f)} of {len(cat)} organisations")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Shown", len(f))
    k2.metric("With careers page", int(f["has_careers"].sum()))
    k3.metric("Anthropology / PhD", int(f["phd_relevant"].sum()))
    k4.metric("Latin America", int(f["latam_relevant"].sum()))
    k5.metric("Remote-friendly", int(f["remote_friendly"].sum()))
    st.divider()

    if f.empty:
        st.info("No organisations match these filters.")
        st.stop()

    # Refresh the whole filtered set. Capped so a stray "no filters" click
    # doesn't kick off 665 live searches; narrow the filters for a big sweep.
    rc1, rc2 = st.columns([3, 1])
    with rc2:
        if st.button(f"🔄 Refresh these {len(f)}", use_container_width=True,
                     disabled=len(f) > 60,
                     help="Re-search every organisation shown. Filter to ≤60 "
                          "first; larger sweeps belong on the CLI "
                          "(python -m jobsearch.enrich)."):
            prog = st.progress(0.0, "Refreshing…")
            changed = 0
            rows = f.to_dict("records")
            for i, rr in enumerate(rows, 1):
                try:
                    new = store.refresh_org(
                        rr["id"], rr["organisation"], base=rr["base"],
                        existing_url=rr["careers_url"], category=rr["category"],
                    )
                    if new.get("url") and new.get("url") != rr["careers_url"]:
                        changed += 1
                except Exception:
                    pass
                prog.progress(i / len(rows), f"{i}/{len(rows)}…")
            load_catalogue.clear()
            st.success(f"Refreshed {len(rows)} — {changed} URLs changed.")
            st.rerun()

    view = f.sort_values(["sector", "organisation"])
    # Sector and Type are both filters already; showing Type here as well was
    # pushing the careers link off the right edge.
    table = pd.DataFrame({
        "": view["careers_confidence"].map(lambda c: CONF_ICON.get(c, "⚪")),
        "Organisation": view["organisation"],
        "Sector": view["sector"],
        "Based in": view["base"],
        "Lang": view["languages"],
        "Size": view["size"],
        "Updated": view["last_updated"].replace("", "—"),
        "Score": view["careers_score"],
        "Careers": view["careers_url"],
    })
    st.dataframe(
        table, hide_index=True, use_container_width=True, height=420,
        column_config={
            "": st.column_config.TextColumn("", width="small",
                                            help="Careers-page confidence"),
            "Organisation": st.column_config.TextColumn(width="large"),
            "Sector": st.column_config.TextColumn(width="medium"),
            "Based in": st.column_config.TextColumn(width="small"),
            "Careers": st.column_config.LinkColumn("Careers", display_text="Open ↗",
                                                   width="small"),
            "Size": st.column_config.NumberColumn(
                format="localized",
                help="Population (communes) or students (universities)",
            ),
            "Updated": st.column_config.TextColumn(
                width="small", help="When the careers page last changed"
            ),
            "Score": st.column_config.NumberColumn(
                width="small", format="%d",
                help=f"Evidence total. ≥{HIGH_THRESHOLD} high, ≥{THRESHOLD} medium.",
            ),
        },
    )
    st.download_button(
        "Download as CSV", view.to_csv(index=False).encode(),
        file_name="brussels_organisations.csv", mime="text/csv",
    )

    st.divider()
    st.subheader("Organisation detail")
    pick = st.selectbox("Choose an organisation", view["organisation"].tolist())
    r = view[view["organisation"] == pick].iloc[0]

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"### {r['organisation']}")
        st.markdown(
            f"<span style='color:{MUTED}'>{r['sector']}"
            + (f" · {r['type']}" if r["type"] else "")
            + (f" · {r['base']}" if r["base"] else "")
            + "</span>",
            unsafe_allow_html=True,
        )
        if r["description"]:
            st.write(r["description"])
        if r["target_roles"]:
            st.markdown(f"**Roles to look for:** {r['target_roles']}")
        if r["why_fits"] and r["why_fits"] != r["description"]:
            st.markdown(f"**Why it fits:** {r['why_fits']}")
        tags = []
        if r["phd_relevant"]:
            tags.append("🎓 anthropology / PhD route")
        if r["latam_relevant"]:
            tags.append("🌎 Latin America / Spanish")
        if r["remote_friendly"]:
            tags.append("🏠 hires remote / worldwide")
        if tags:
            st.markdown(" · ".join(tags))
    with c2:
        if r["languages"]:
            st.metric("Working language", r["languages"])
        if pd.notna(r["size"]) and r["size"]:
            label = ("Population" if r["sector"] == "Commune / local government"
                     else "Students" if r["sector"] == "University & research"
                     else "Size")
            st.metric(label, f"{int(r['size']):,}")
        if r["careers_url"]:
            conf = r["careers_confidence"]
            st.markdown(f"{CONF_ICON.get(conf,'⚪')} **[Careers page ↗]({r['careers_url']})**")
            st.caption(f"Confidence: {conf or 'unknown'} · score {r['careers_score']}")
            if len(r["careers_reasons"]):
                with st.expander("Why this page?"):
                    for reason in r["careers_reasons"]:
                        st.caption(f"· {reason}")
            if r["last_updated"]:
                trust = r["last_updated_trust"]
                st.caption(f"Last updated {r['last_updated']} — source: "
                           f"{TRUST_NOTE.get(trust, 'unknown')}")
            else:
                st.caption("This page publishes no last-updated date.")
        elif r["search_url"]:
            st.markdown(f"⚪ [Search for it ↗]({r['search_url']})")
            st.caption("No careers page found with enough confidence.")
        if r["homepage"]:
            st.markdown(f"[Homepage ↗]({r['homepage']})")
        if len(r["sources"]):
            st.caption("Source: " + ", ".join(r["sources"]))

        # --- user actions: mark checked, and refresh the URL ---------------
        st.divider()
        if r["last_check_verdict"]:
            when = str(r["last_check_at"])[:10]
            st.caption(f"You last marked this **{r['last_check_verdict']}** "
                       f"on {when}.")

        VERDICTS = {
            "good": "✅ Good link", "wrong": "❌ Wrong page",
            "dead": "💀 Dead / 404", "applied": "📮 Applied",
            "not_relevant": "🚫 Not relevant",
        }
        st.caption("Mark this link, once you've looked:")
        vcols = st.columns(len(VERDICTS))
        for col, (verdict, lbl) in zip(vcols, VERDICTS.items()):
            if col.button(lbl, key=f"v_{r['id']}_{verdict}",
                          use_container_width=True):
                try:
                    store.log_check(r["id"], r["version_id"], verdict,
                                    r["careers_url"])
                    load_catalogue.clear()
                    st.success(f"Logged: {verdict}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not save: {e}")

        if st.button("🔄 Refresh this URL", key=f"refresh_{r['id']}"):
            with st.spinner(f"Re-searching for {r['organisation']}…"):
                try:
                    new = store.refresh_org(
                        r["id"], r["organisation"], base=r["base"],
                        existing_url=r["careers_url"], category=r["category"],
                    )
                    load_catalogue.clear()
                    if new.get("url") and new.get("url") != r["careers_url"]:
                        st.success(f"New URL found: {new['url']}")
                    else:
                        st.info("No change — the current URL is still the best match.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Refresh failed: {e}")

        # --- URL history --------------------------------------------------
        with st.expander("URL history"):
            try:
                hist = store.version_history(r["id"])
            except Exception:
                hist = []
            if len(hist) <= 1:
                st.caption("Only one version on record so far.")
            for v in hist:
                tag = "current" if not v.get("superseded") else "superseded"
                st.caption(
                    f"**{tag}** · {str(v.get('discovered_at',''))[:10]} · "
                    f"score {v.get('score','?')} · [{v.get('url','')[:60]}]"
                    f"({v.get('url','')})"
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
