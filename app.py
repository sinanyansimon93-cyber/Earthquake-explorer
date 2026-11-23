import pandas as pd
import streamlit as st
from google.cloud import bigquery


PROJECT_ID = "eartquake-bigquery"
DATASET_ID = f"{PROJECT_ID}.someidforbigquery"
TABLE_ID = f"{DATASET_ID}.earthquakes"


st.set_page_config(
    page_title="Earthquake Explorer",
    page_icon="🌍",
    layout="wide",
)


@st.cache_data(ttl=300, show_spinner=False)
def load_earthquakes():
    """Read saved history from BigQuery. Does not contact USGS."""
    sql = f"""
        SELECT
            earthquake_id,
            event_time,
            place,
            magnitude,
            longitude,
            latitude,
            depth_km
        FROM `{TABLE_ID}`
        WHERE event_time BETWEEN
            TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            AND CURRENT_TIMESTAMP()
        ORDER BY event_time DESC
    """

    with bigquery.Client(project=PROJECT_ID) as client:
        dataset = client.get_dataset(DATASET_ID)

        result = client.query(
            sql,
            location=dataset.location,
        ).result()

        records = [dict(row.items()) for row in result]

    df = pd.DataFrame(records)

    if not df.empty:
        df["event_time"] = pd.to_datetime(
            df["event_time"],
            utc=True,
        )

        for column in [
            "magnitude",
            "longitude",
            "latitude",
            "depth_km",
        ]:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    return df


st.title("🌍 Earthquake Explorer")
st.caption("USGS • Magnitude 2.5+ • Saved history: past 30 days")


# Load saved data immediately when the page opens.
try:
    with st.spinner("Loading earthquake history from BigQuery..."):
        df = load_earthquakes()
except Exception as error:
    st.error(f"Could not read earthquake history: {error}")
    st.stop()


if df.empty:
    st.info("No saved earthquakes within the past 30 days.")
    st.stop()


latest_event = df["event_time"].max()

st.caption(
    f"Source: BigQuery · Stored events in this period: {len(df):,}"
)

st.caption(
    "Latest recorded earthquake: "
    + latest_event.strftime("%Y-%m-%d %H:%M:%S UTC")
)


# Filters affect only the display.
st.sidebar.header("Filters")

location = st.sidebar.text_input(
    "Search location",
    placeholder="For example: Japan",
)

minimum = st.sidebar.number_input(
    "Minimum magnitude",
    min_value=0.0,
    max_value=10.0,
    value=0.0,
    step=0.5,
)

include_unknown = st.sidebar.checkbox(
    "Include missing magnitudes",
    value=True,
)


magnitude_mask = df["magnitude"].ge(minimum)

if include_unknown:
    magnitude_mask = magnitude_mask | df["magnitude"].isna()

location_mask = df["place"].fillna("").str.contains(
    location,
    case=False,
    regex=False,
)

filtered = df[magnitude_mask & location_mask].copy()


# Summary for the displayed records.
first, second, third = st.columns(3)

first.metric("Earthquakes shown", len(filtered))

magnitudes = filtered["magnitude"].dropna()

second.metric(
    "Strongest magnitude",
    f"{magnitudes.max():.1f}" if not magnitudes.empty else "—",
)

depths = filtered["depth_km"].dropna()

third.metric(
    "Average depth",
    f"{depths.mean():.1f} km" if not depths.empty else "—",
)


if filtered.empty:
    st.info("No earthquakes match your filters.")
    st.stop()


map_tab, table_tab = st.tabs(["Map", "All records"])

with map_tab:
    points = filtered[["latitude", "longitude"]].dropna()

    if not points.empty:
        st.map(points)
    else:
        st.info("No coordinates available for these records.")


with table_tab:
    displayed = filtered.sort_values(
        "event_time",
        ascending=False,
    )

    st.dataframe(
        displayed,
        hide_index=True,
    )

    st.download_button(
        "Download displayed records as CSV",
        data=displayed.to_csv(index=False).encode("utf-8"),
        file_name="earthquakes.csv",
        mime="text/csv",
    )