"""Fire or Factory? A cleaned satellite fire record for Sweden.

Reads only the small files in app/data/ so it runs anywhere.
"""

from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

HERE = Path(__file__).parent
DATA = HERE / "data"

FIRE = [230, 85, 13]  # orange
FACTORY = [49, 130, 189]  # blue
VERSIONS = {"ours": "Our cleaning", "firms": "FIRMS labels", "raw": "Raw (no cleaning)"}
FAMILIES = {
    "ALL": "MODIS + VIIRS",
    "MODIS": "MODIS only (from 2000)",
    "VIIRS": "VIIRS only (from 2012)",
}

st.set_page_config(page_title="Fire or Factory?", layout="wide")


@st.cache_data
def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detections = pd.read_parquet(DATA / "detections.parquet")
    calendar = pd.read_csv(DATA / "fire_calendar.csv")
    disagreements = pd.read_csv(DATA / "disagreements.csv")
    return detections, calendar, disagreements


def is_static(df: pd.DataFrame, version: str) -> pd.Series:
    """Which detections count as factory in the chosen version."""
    if version == "ours":
        return df["is_static"]
    if version == "firms":
        return df["firms_static"]
    return pd.Series(False, index=df.index)  # raw: everything counts as fire


detections, calendar, disagreements = load()

# Header
st.title("Fire or Factory?")
st.markdown(
    "Satellites detect **heat**, not fire. Over Sweden, much of what NASA's FIRMS hotspot "
    "data shows as fire is really **steelworks, smelters, refineries and cement plants**. "
    "This app separates the two, using how often each place lights up over 25 years "
    "of MODIS and VIIRS data."
)


# Controls
with st.sidebar:
    st.header("Show")
    version = st.radio("Labels", list(VERSIONS), format_func=VERSIONS.get)
    family = st.radio("Satellites", list(FAMILIES), format_func=FAMILIES.get)
    years = st.slider("Years", 2001, 2025, (2018, 2018))

tab_map, tab_calendar, tab_disagree, tab_about = st.tabs(
    ["Map", "Fire calendar", "Where we disagree with FIRMS", "Method and limits"]
)

# Map
with tab_map:
    d = detections[detections["year"].between(*years)]
    if family != "ALL":
        d = d[d["family"] == family]
    static = is_static(d, version)
    d = d.assign(
        kind=static.map({True: "factory", False: "fire"}),
        color=static.map(lambda s: FACTORY if s else FIRE),
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Detections", f"{len(d):,}")
    c2.metric("Fire", f"{(~static).sum():,}")
    c3.metric("Factory / static", f"{static.sum():,}")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=d[["longitude", "latitude", "color", "kind", "date_utc", "family"]],
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_radius=600,
        radius_min_pixels=2,
        opacity=0.7,
        pickable=True,
    )
    view = pdk.ViewState(latitude=62.5, longitude=16.5, zoom=4)
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            map_style="light",
            tooltip={"text": "{kind}\n{date_utc}\n{family}"},
        ),
        height=650,
    )
    st.caption(
        "Orange: fire. Blue: factory or other static heat source. "
        "Each dot is one hot pixel seen by one satellite pass."
    )

# Fire calendar
with tab_calendar:
    st.subheader(f"Fire-days per month: {VERSIONS[version]}, {FAMILIES[family]}")
    st.caption(
        "A fire-day is one ~1 km grid cell with fire on one date. Many pixels, "
        "passes and satellites seeing the same fire that day count once."
    )
    sel = calendar[
        (calendar["family"] == family)
        & (calendar["version"] == version)
        & calendar["year"].between(*years)
    ]
    heat = (
        alt.Chart(sel)
        .mark_rect()
        .encode(
            x=alt.X("month:O", title="Month"),
            y=alt.Y("year:O", title="Year"),
            color=alt.Color("fire_days:Q", title="Fire-days", scale=alt.Scale(scheme="orangered")),
            tooltip=["year", "month", "fire_days"],
        )
    )
    st.altair_chart(heat, width="stretch")

    st.subheader("Fire-days per year: raw vs FIRMS vs our cleaning")
    yearly = (
        calendar[calendar["family"] == family]
        .groupby(["year", "version"], as_index=False)["fire_days"]
        .sum()
    )
    yearly["version"] = yearly["version"].map(VERSIONS)
    lines = (
        alt.Chart(yearly)
        .mark_line(point=True)
        .encode(
            x=alt.X("year:O", title="Year"),
            y=alt.Y("fire_days:Q", title="Fire-days"),
            color=alt.Color("version:N", title=None, sort=list(VERSIONS.values())),
            tooltip=["year", "version", "fire_days"],
        )
    )
    st.altair_chart(lines, width="stretch")
    st.caption(
        "VIIRS starts in 2012 and NOAA-20 adds a second VIIRS satellite from April 2018, "
        "so 'MODIS + VIIRS' is not comparable across those years. "
        "MODIS only is the one consistent series from 2001."
    )

# Disagreements
with tab_disagree:
    st.markdown(
        "Grid cells where our label and FIRMS's label disagree most, over all years. "
        "**we_static**: we say factory, FIRMS says fire. **we_fire**: the opposite. "
        "Open a location in satellite view to check it yourself."
    )
    table = disagreements.assign(
        map=lambda t: (
            "https://www.google.com/maps?t=k&q=" + t["lat"].astype(str) + "," + t["lon"].astype(str)
        )
    )[["lat", "lon", "we_static", "we_fire", "cell_days", "cell_months", "families", "map"]]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={"map": st.column_config.LinkColumn("Satellite view", display_text="open")},
    )

# Method and limits
with tab_about:
    st.markdown(
        """
**Data.** NASA FIRMS archive (standard processing) hotspots for MODIS (2000-), VIIRS S-NPP
(2012-) and VIIRS NOAA-20 (2018-), clipped to Sweden with a 2 km sea buffer.

**Method.** Every detection is placed in a ~1 km grid cell. Each cell gets its history: active
days, months, years, night share and typical power, plus the history of the busiest cell in its
3x3 block. A gradient-boosted classifier, trained on FIRMS's own VIIRS labels and scored on
grid cells it never saw, gives each detection a probability of being static. It is then applied
to MODIS too, so VIIRS's sharper view corrects MODIS's weaker labels.

**Limits.**
- There is no ground truth: agreement with FIRMS is not the same as being right.
- A simple rule (active in 6+ months = static) is almost as good as the classifier.
- Some MODIS detections that FIRMS calls static are single daytime detections we call fire,
  with 1-2 days of evidence these are genuinely ambiguous.
- Site names are matched from coordinates and should be checked on a map.
        """
    )
