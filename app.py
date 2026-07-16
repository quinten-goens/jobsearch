"""Streamlit UI for the Brussels job search.

    streamlit run app.py

The product here is the filterable list -- Sarah needs to find and act on
postings, so the table is the point. The charts are context, not decoration.
"""
import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

from jobsearch.config import JOBS_JSON
from jobsearch.discover import DISCOVERED_JSON

st.set_page_config(page_title="Brussels job search", page_icon="🇧🇪", layout="wide")

# Categorical slots 1-3 from the validated reference palette. Only three are
# needed (source is the only categorical encoding), which sits inside the
# comfortable band where color alone is safe.
SERIES = ["#2a78d6", "#008300", "#e87ba4"]
MUTED = "#898781"

# Roles Sarah is actually targeting: policy/IR, 2-5 years, FR/ES/EN.
GOOD_TITLE = (
    "policy", "adviser", "advisor", "advocacy", "public affairs", "programme",
    "program", "project", "communications", "campaign", "eu affairs",
    "international", "human rights", "migration", "development", "research",
)


@st.cache_data(ttl=300)
def load_jobs() -> tuple[pd.DataFrame, str]:
    if not JOBS_JSON.exists():
        return pd.DataFrame(), ""
    payload = json.loads(JOBS_JSON.read_text())
    df = pd.DataFrame(payload.get("jobs", []))
    if df.empty:
        return df, payload.get("generated_at", "")

    for col in ("title", "employer", "location", "category", "source",
                "url", "posted", "deadline", "confidence", "method"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")

    df["posted_dt"] = pd.to_datetime(df["posted"], errors="coerce")
    df["deadline_dt"] = pd.to_datetime(df["deadline"], errors="coerce")
    today = pd.Timestamp(date.today())
    df["days_left"] = (df["deadline_dt"] - today).dt.days
    df["age_days"] = (today - df["posted_dt"]).dt.days
    df["brussels"] = df["location"].str.contains(
        "brussel|bruxelles|belgium|belgique", case=False, na=False
    )
    df["good_fit"] = df["title"].str.lower().str.contains(
        "|".join(GOOD_TITLE), na=False
    )
    return df, payload.get("generated_at", "")


@st.cache_data(ttl=300)
def load_discovery() -> pd.DataFrame:
    if not DISCOVERED_JSON.exists():
        return pd.DataFrame()
    return pd.DataFrame(json.loads(DISCOVERED_JSON.read_text()))


df, generated_at = load_jobs()

st.title("Brussels job search")
if df.empty:
    st.warning(
        "No jobs yet. Run `python -m jobsearch.pipeline --boards` to populate "
        "`data/jobs.json`."
    )
    st.stop()

when = ""
if generated_at:
    try:
        when = datetime.fromisoformat(generated_at).strftime("%d %b %Y, %H:%M")
    except ValueError:
        when = generated_at
st.caption(f"{len(df)} postings · last scraped {when}")

# ---------------------------------------------------------------- filters row
c1, c2, c3, c4 = st.columns([2, 1.4, 1.4, 1.2])
with c1:
    q = st.text_input("Search title or employer", placeholder="e.g. policy officer")
with c2:
    sources = st.multiselect("Source", sorted(df["source"].unique()))
with c3:
    freshness = st.selectbox(
        "Posted", ["Any time", "Last 7 days", "Last 14 days", "Last 30 days"]
    )
with c4:
    only_open = st.checkbox("Hide expired", value=True)

f = df.copy()
if q:
    mask = (
        f["title"].str.contains(q, case=False, na=False)
        | f["employer"].str.contains(q, case=False, na=False)
    )
    f = f[mask]
if sources:
    f = f[f["source"].isin(sources)]
if freshness != "Any time":
    days = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30}[freshness]
    f = f[f["age_days"].le(days) | f["age_days"].isna()]
if only_open:
    f = f[f["days_left"].isna() | f["days_left"].ge(0)]

# ------------------------------------------------------------------- KPI row
# A handful of headline numbers is a KPI row, not a bar chart.
k1, k2, k3, k4 = st.columns(4)
k1.metric("Matching now", len(f))
k2.metric("In Brussels", int(f["brussels"].sum()))
k3.metric("Posted this week", int(f["age_days"].le(7).sum()))
closing = f["days_left"].le(7) & f["days_left"].ge(0)
k4.metric("Closing within 7 days", int(closing.sum()))

st.divider()

left, right = st.columns([3, 1])

with left:
    st.subheader("Postings")
    if f.empty:
        st.info("No postings match these filters.")
    else:
        view = f.sort_values("posted_dt", ascending=False, na_position="last")
        table = pd.DataFrame({
            "Title": view["title"],
            "Employer": view["employer"].replace("", "—"),
            "Location": view["location"].replace("", "—"),
            "Posted": view["posted_dt"].dt.strftime("%d %b").fillna("—"),
            "Deadline": view["deadline_dt"].dt.strftime("%d %b").fillna("—"),
            "Left": view["days_left"],
            "Link": view["url"],
        })
        # Source is deliberately not a column: it's already a filter and a
        # chart, and the extra width was pushing the link off the edge.
        st.dataframe(
            table,
            hide_index=True,
            use_container_width=True,
            height=560,
            column_config={
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Employer": st.column_config.TextColumn("Employer", width="medium"),
                "Location": st.column_config.TextColumn("Location", width="small"),
                "Link": st.column_config.LinkColumn(
                    "Link", display_text="Open ↗", width="small"
                ),
                "Left": st.column_config.NumberColumn(
                    "Left", format="%dd", help="Days until the deadline"
                ),
            },
        )
        st.download_button(
            "Download these as CSV",
            view.drop(columns=[c for c in ("posted_dt", "deadline_dt") if c in view])
                .to_csv(index=False).encode(),
            file_name="brussels_jobs.csv",
            mime="text/csv",
        )

with right:
    st.subheader("New postings per week")
    # Trend over time: a line/area on one series. Sequential, not categorical.
    weekly = (
        f.dropna(subset=["posted_dt"])
        .set_index("posted_dt")
        .resample("W-MON")
        .size()
    )
    if len(weekly) > 1:
        st.area_chart(weekly, color=SERIES[0], height=200)
    else:
        st.caption("Not enough dated postings yet to show a trend.")

    st.subheader("Where they come from")
    by_source = f["source"].value_counts()
    if not by_source.empty:
        # Magnitude comparison, low->high: bars in one hue, not a pie.
        st.bar_chart(by_source, color=SERIES[0], height=200, horizontal=True)

    st.subheader("Closing soonest")
    soon = (
        f[f["days_left"].ge(0)]
        .sort_values("days_left")
        .head(6)
    )
    if soon.empty:
        st.caption("No dated deadlines in this selection.")
    for _, r in soon.iterrows():
        d = int(r["days_left"])
        urgency = "🔴" if d <= 3 else ("🟠" if d <= 7 else "⚪")
        st.markdown(
            f"{urgency} **[{r['title'][:52]}]({r['url']})**  \n"
            f"<span style='color:{MUTED}'>{r['employer'][:40]} · "
            f"{d} day{'s' if d != 1 else ''} left</span>",
            unsafe_allow_html=True,
        )

# --------------------------------------------------------- discovery coverage
disc = load_discovery()
if not disc.empty:
    with st.expander(
        f"Careers-page discovery — {len(disc)} of 282 organisations resolved"
    ):
        st.caption(
            "Each organisation's careers page, found by searching and scoring "
            "the top results. 'high' means several independent signals agreed; "
            "'medium' is worth a glance before trusting."
        )
        counts = disc["confidence"].value_counts()
        cols = st.columns(len(counts))
        for col, (label, n) in zip(cols, counts.items()):
            col.metric(str(label), int(n))
        st.dataframe(
            pd.DataFrame({
                "Organisation": disc["organisation"],
                "Careers page": disc["careers_url"],
                "Confidence": disc["confidence"],
                "Score": disc["score"],
                "Fallback search": disc["search_url"],
            }),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Careers page": st.column_config.LinkColumn(display_text="Open"),
                "Fallback search": st.column_config.LinkColumn(display_text="Search"),
            },
        )
