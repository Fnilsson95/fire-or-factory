"""Export: small files for the Streamlit app.

data/clean/ is gitignored, so the deployed app cant read it. This step writes slim copies
of the results into app/data/, which is committed and shipped with the app.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from fof.fire_calendar import OUT_PATH as CALENDAR_PATH
from fof.model import OUT_PATH as CLASSIFIED_PATH
from fof.model import disagreements

APP_DATA = Path("app/data")

# Only what the app shows. Everything else stays in data/clean/.
APP_COLUMNS = [
    "latitude", "longitude", "date_utc", "year", "month", "family",
    "firms_static", "is_static", "p_static", "cell_days", "cell_months",
]


def export_app_data(
    classified_path: Path = CLASSIFIED_PATH,
    calendar_path: Path = CALENDAR_PATH,
    out_dir: Path = APP_DATA,
) -> None:
    df = pd.read_parquet(classified_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    slim = df[APP_COLUMNS].copy()
    slim["latitude"] = slim["latitude"].round(4)  # ~10 m, far finer than a pixel
    slim["longitude"] = slim["longitude"].round(4)
    slim["p_static"] = slim["p_static"].round(3)
    slim["date_utc"] = slim["date_utc"].dt.date.astype(str)
    slim.to_parquet(out_dir / "detections.parquet", index=False)

    shutil.copy(calendar_path, out_dir / "fire_calendar.csv")
    disagreements(df, n=50).reset_index().to_csv(out_dir / "disagreements.csv", index=False)

    for f in sorted(out_dir.iterdir()):
        print(f"wrote {f} ({f.stat().st_size / 1e6:.2f} MB)")
