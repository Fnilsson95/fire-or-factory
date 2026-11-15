"""Features - grid-cell history and per-detection features for the classifier

Every detection is places in a ca 1km grid cell. Cell features describe that cells history
(how often it is active, how spread over the year, how much at night, etc)
Detection features describe the single observation

FIRMS own "firms_type" is NOT a feature, it is what we compare against and a model
trained on it would just learn to copy FIRMS.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fof.normalise import OUT_PATH as DETECTIONS_PATH

OUT_PATH = Path("data/clean/features.parquet")
CELL_KM = 1.0  # grid size
KM_PER_DEG_LAT = 111.32
CONFIDENCE_RANK = {"low": 0, "nominal": 1, "high": 2}

DETECTION_FEATURES = ["frp", "bt_diff", "is_night", "is_viirs", "confidence_rank", "day_of_year"]
CELL_FEATURES = [
    "cell_detections",
    "cell_days",
    "cell_months",
    "cell_years",
    "cell_span_days",
    "cell_night_share",
    "cell_frp_median",
]

# History of the busiest cell in each cell's 3x3 block (itself and its 8 neighbours).
BLOCK_FEATURES = ["block_days", "block_months", "block_span_days", "block_night_share"]

FEATURES = DETECTION_FEATURES + CELL_FEATURES + BLOCK_FEATURES


def add_detection_features(df: pd.DataFrame) -> pd.DataFrame:
    """Featutes from the single observation"""
    return df.assign(
        bt_diff=df["bt_fire"] - df["bt_background"],
        is_night=(df["daynight"] == "N").astype(int),
        is_viirs=(df["family"] == "VIIRS").astype(int),
        confidence_rank=df["confidence_class"].map(CONFIDENCE_RANK),
        day_of_year=df["date_utc"].dt.dayofyear,
        month=df["date_utc"].dt.month,
        year=df["date_utc"].dt.year,
    )


def add_cell_id(df: pd.DataFrame, cell_km: float = CELL_KM) -> pd.DataFrame:
    """Put each detection in a grid cell of roughly cell_km * cell_km

    Latituyde degrees are roughly 111km everywhere, but longitude degrees shrink with cos(latitude)
    so we convert both to km before cutting into cells
    """

    y_km = df["latitude"] * KM_PER_DEG_LAT
    x_km = df["longitude"] * KM_PER_DEG_LAT * np.cos(np.radians(df["latitude"]))
    return df.assign(
        cell_x=np.floor(x_km / cell_km).astype(int),
        cell_y=np.floor(y_km / cell_km).astype(int),
    )


def cell_features(df: pd.DataFrame):
    """One row per cell, summarising everything ever detected in it"""
    cells = df.groupby(["cell_x", "cell_y"]).agg(
        cell_detections=("datetime_utc", "size"),
        cell_days=("date_utc", "nunique"),
        cell_months=("month", "nunique"),
        cell_years=("year", "nunique"),
        cell_first=("date_utc", "min"),
        cell_last=("date_utc", "max"),
        cell_night_share=("is_night", "mean"),
        cell_frp_median=("frp", "median"),
    )
    cells["cell_span_days"] = (cells["cell_last"] - cells["cell_first"]).dt.days + 1
    return cells.drop(columns=["cell_first", "cell_last"])


def block_features(cells: pd.DataFrame) -> pd.DataFrame:
    """For every cell, the history of the busiest cell (most active days) in its 3x3 block.

    Pixel positions wobble ~0.6 km for VIIRS and more for MODIS, so a factory's detections
    spill into neighbouring cells that have a much thinner history of their own. Looking at
    the busiest neighbour lets those edge detections inherit the factory's history.
    """
    columns = ["cell_days", "cell_months", "cell_span_days", "cell_night_share"]
    source = cells[columns].reset_index()
    shifted = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            # Offer this cell's history to its neighbour at (x + dx, y + dy)
            shifted.append(
                source.assign(cell_x=source["cell_x"] + dx, cell_y=source["cell_y"] + dy)
            )
    offers = pd.concat(shifted, ignore_index=True)
    busiest = offers.loc[offers.groupby(["cell_x", "cell_y"])["cell_days"].idxmax()]
    busiest = busiest.set_index(["cell_x", "cell_y"])
    busiest.columns = BLOCK_FEATURES
    return busiest


def build_features(
    in_path: Path = DETECTIONS_PATH, out_path: Path = OUT_PATH, cell_km: float = CELL_KM
) -> pd.DataFrame:
    """Read the clean detections, add all features, write features.parquet"""
    df = pd.read_parquet(in_path)
    df = add_detection_features(df)
    df = add_cell_id(df, cell_km)
    cells = cell_features(df)
    cells = cells.join(block_features(cells))
    df = df.join(cells, on=["cell_x", "cell_y"])


    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    n_cells = df[["cell_x", "cell_y"]].drop_duplicates().shape[0]
    print(f"{len(df):,} detections in {n_cells:,} cells of {cell_km:g} km -> {out_path}")
    # Sanity check - FIRMS-static detections should sit in much busier cells
    summary = df.groupby("firms_static")[CELL_FEATURES + BLOCK_FEATURES].median()
    print("\nMedian cell features, by FIRMS static label:")
    print(summary.round(2).T.to_string())
    return df
