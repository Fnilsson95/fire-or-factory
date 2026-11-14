"""Normalise into one unified, validated table of FIRMS detections over Sweden

Reads the raw CSVs in data/raw/ and harmonises MODIS and VIIRS into one schema
clips to Sweden (data/ref/sweden_clip.geojson)
removes duplicates
validates the results
writes data/clean/detections.parquet
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from shapely import contains_xy
from shapely.geometry import shape

from fof.ingest import RAW_DIR, SOURCES

CLIP_PATH = Path("data/ref/sweden_clip.geojson")
OUT_PATH = Path("data/clean/detections.parquet")


# Same meaning, different names per sensor
RENAME = {
    "brightness": "bt_fire",  # MODIS channel 21/22
    "bright_ti4": "bt_fire",  # VIIRS I4
    "bright_t31": "bt_background",  # MODIS channel 31
    "bright_ti5": "bt_background",  # VIIRS I5
    "scan": "scan_km",
    "track": "track_km",
    "confidence": "confidence_raw",
    "type": "firms_type",
}

SATELLITE = {
    "Terra": "Terra",
    "Aqua": "Aqua",
    "T": "Terra",
    "A": "Aqua",
    "N": "SNPP",
    "N20": "NOAA-20",
}

VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}

COLUMNS = [
    "datetime_utc",
    "date_utc",
    "source",
    "family",
    "satellite",
    "latitude",
    "longitude",
    "scan_km",
    "track_km",
    "bt_fire",
    "bt_background",
    "frp",
    "daynight",
    "confidence_raw",
    "confidence_class",
    "firms_type",
    "firms_static",
    "version",
]

SCHEMA = pa.DataFrameSchema(
    {
        "datetime_utc": pa.Column("datetime64[ns, UTC]", coerce=True),
        "date_utc": pa.Column("datetime64[ns]", coerce=True),
        "source": pa.Column(str, pa.Check.isin(SOURCES)),
        "family": pa.Column(str, pa.Check.isin(["MODIS", "VIIRS"])),
        "satellite": pa.Column(str, pa.Check.isin(sorted(set(SATELLITE.values())))),
        "latitude": pa.Column(float, pa.Check.in_range(55.0, 69.5)),
        "longitude": pa.Column(float, pa.Check.in_range(10.5, 24.5)),
        "scan_km": pa.Column(float, pa.Check.in_range(0.2, 5.0)),
        "track_km": pa.Column(float, pa.Check.in_range(0.2, 5.0)),
        "bt_fire": pa.Column(float, pa.Check.in_range(200, 550)),  # Kelvin
        "bt_background": pa.Column(float, pa.Check.in_range(200, 550)),
        "frp": pa.Column(float, pa.Check.ge(0)),  # megawatts
        "daynight": pa.Column(str, pa.Check.isin(["D", "N"])),
        "confidence_raw": pa.Column(str),
        "confidence_class": pa.Column(str, pa.Check.isin(["low", "nominal", "high"])),
        "firms_type": pa.Column(int, pa.Check.isin([0, 1, 2, 3])),
        "firms_static": pa.Column(bool),
        "version": pa.Column(str),
    },
    unique=["source", "datetime_utc", "latitude", "longitude"],
    strict=True,
)


def read_source(source: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """All raw files for one source stacked into one table with a "source" column"""

    frames = [
        pd.read_csv(f, dtype={"confidence": str, "version": str})
        for f in sorted(raw_dir.glob(f"{source}_*.csv"))
    ]
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["source"] = source
    return df


def confidence_class(df: pd.DataFrame) -> pd.Series:
    """VIIRS l/n/h and MODIS 0-100 on one scale
    (FIRMS MODIES <30 low, 30-79 normal, 80+ high)
    """

    viirs = df["confidence_raw"].map(VIIRS_CONFIDENCE)
    modis_pct = pd.to_numeric(df["confidence_raw"], errors="coerce")
    modis = pd.cut(modis_pct, bins=[-1, 29, 79, 100], labels=["low", "nominal", "high"])
    return viirs.where(df["family"] == "VIIRS", modis.astype(str))


def harmonise(df: pd.DataFrame) -> pd.DataFrame:
    """One raw source table into the unified schema."""
    df = df.rename(columns=RENAME)
    df["family"] = df["source"].str.split("_").str[0]
    df["satellite"] = df["satellite"].map(SATELLITE)

    # acq_time is HHMM without leading zeros, in UTC: 10 -> 00:10, 1018 -> 10:18.
    hhmm = df["acq_time"].astype(int)
    df["date_utc"] = pd.to_datetime(df["acq_date"])
    df["datetime_utc"] = (
        df["date_utc"]
        + pd.to_timedelta(hhmm // 100, unit="h")
        + pd.to_timedelta(hhmm % 100, unit="m")
    ).dt.tz_localize("UTC")

    df["confidence_class"] = confidence_class(df)
    # Type 3 ("offshore") is coastal industry in Sweden, so 2 and 3 both mean static.
    df["firms_static"] = df["firms_type"].isin([2, 3])
    return df[COLUMNS]


def load_clip(path: Path = CLIP_PATH):
    return shape(json.loads(path.read_text())["geometry"])


def normalise(
    raw_dir: Path = RAW_DIR, clip_path: Path = CLIP_PATH, out_path: Path = OUT_PATH
) -> pd.DataFrame:
    """Run the whole step and write the parquet file. Prints how many rows each step drops."""
    tables = [harmonise(t) for s in SOURCES if len(t := read_source(s, raw_dir))]
    df = pd.concat(tables, ignore_index=True)
    print(f"read:        {len(df):>8,} rows")

    inside = contains_xy(load_clip(clip_path), df["longitude"], df["latitude"])
    df = df[inside]
    print(f"in Sweden:   {len(df):>8,} rows")

    df = df.drop_duplicates(subset=["source", "datetime_utc", "latitude", "longitude"])
    print(f"unique:      {len(df):>8,} rows")

    df = df.sort_values(["datetime_utc", "source"]).reset_index(drop=True)
    df = SCHEMA.validate(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"wrote {out_path}")
    print(df.groupby(["source", "firms_static"]).size().unstack(fill_value=0).to_string())
    return df
