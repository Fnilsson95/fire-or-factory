"""Fire calendar: fire-days per year and month, raw vs FIRMS-cleaned vs our cleaning.

Named fire_calendar rather than calendar to avoid confusion with the standard library module.

Unit: a fire-day is one ~1 km grid cell with at least one fire detection on one UTC date.
Many pixels, passes and satellites seeing the same fire on the same day count once.

Three versions, so the effect of cleaning is visible:
    raw    every detection counts as fire
    firms  FIRMS's labels: type 2 or 3 (static) removed
    ours   our classifier: detections with is_static removed

Each is given for MODIS only, VIIRS only and both combined. MODIS only is the one
consistent series from 2000. VIIRS starts in 2012 and NOAA-20 adds a second VIIRS
satellite from April 2018, so "both" is not comparable across those years.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fof.model import OUT_PATH as CLASSIFIED_PATH

OUT_PATH = Path("data/clean/fire_calendar.csv")
VERSIONS = ("raw", "firms", "ours")
FAMILIES = ("ALL", "MODIS", "VIIRS")


def fire_mask(df: pd.DataFrame, version: str) -> pd.Series:
    """Which detections count as fire in a given version."""
    if version == "raw":
        return pd.Series(True, index=df.index)
    if version == "firms":
        return ~df["firms_static"]
    if version == "ours":
        return ~df["is_static"]
    raise ValueError(version)


def fire_days(df: pd.DataFrame) -> pd.Series:
    """Distinct (cell, date) pairs per year and month."""
    days = df[["cell_x", "cell_y", "date_utc", "year", "month"]].drop_duplicates(
        subset=["cell_x", "cell_y", "date_utc"]
    )
    return days.groupby(["year", "month"]).size()


def build_calendar(in_path: Path = CLASSIFIED_PATH, out_path: Path = OUT_PATH) -> pd.DataFrame:
    """Long table: year, month, family, version, fire_days. Months with no fires are 0."""
    df = pd.read_parquet(in_path)
    years = range(df["year"].min(), df["year"].max() + 1)
    all_months = pd.MultiIndex.from_product([years, range(1, 13)], names=["year", "month"])

    parts = []
    for family in FAMILIES:
        sub = df if family == "ALL" else df[df["family"] == family]
        for version in VERSIONS:
            counts = fire_days(sub[fire_mask(sub, version)])
            counts = counts.reindex(all_months, fill_value=0)
            parts.append(
                counts.rename("fire_days").reset_index().assign(family=family, version=version)
            )
    cal = pd.concat(parts, ignore_index=True)[["year", "month", "family", "version", "fire_days"]]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cal.to_csv(out_path, index=False)
    print(f"wrote {out_path} ({len(cal):,} rows)")

    yearly = cal.pivot_table(
        index=["year", "family"], columns="version", values="fire_days", aggfunc="sum"
    )[list(VERSIONS)]
    yearly["removed_by_ours_%"] = (100 * (1 - yearly["ours"] / yearly["raw"])).round(1)
    print("\nFire-days per year:")
    print(yearly.to_string())
    return cal


def month_grid(cal: pd.DataFrame, family: str = "ALL", version: str = "ours") -> pd.DataFrame:
    """Year x month grid of fire-days for one family and version (for printing and the app)."""
    sel = cal[(cal["family"] == family) & (cal["version"] == version)]
    return sel.pivot(index="year", columns="month", values="fire_days")
