"""Ingest FIRMS area API into untouched raw CSV files, one file per source and 5-day chunk.

Raw files are never modified. Existing chunks are skipped, so reruns resume where they stopped.
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# west, south, east, north. A box around Sweden. The exact border is applied later.
SWEDEN_BBOX = (10.9, 55.3, 24.2, 69.1)

# Standard-processing (archive quality) products.
# MODIS_SP - Terra and Aqua satellites, 1km pixels (from 2000)
# VIIRS_SNPP_SP - 375m pixels (from 2012)
# VIIRS_NOAA20_SP - same instrument as VIIRS_SNPP_SP (from 2018)
SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP")
MAX_DAYS = 5  # API limit per request
RAW_DIR = Path("data/raw")


# Read the env file
def get_key() -> str:
    load_dotenv()
    key = os.environ.get("FIRMS_MAP_KEY", "").strip().strip('"')
    if not key:
        raise RuntimeError("FIRMS_MAP_KEY is not set (put it in .env)")
    return key


def chunks(start: date, end: date, size: int = MAX_DAYS):
    """Yield (chunk_start, n_days) covering start..end inclusive."""
    current = start
    while current <= end:
        n = min(size, (end - current).days + 1)
        yield current, n
        current += timedelta(days=n)


def fetch_chunk(client: httpx.Client, key: str, source: str, start: date, n_days: int) -> str:
    bbox = ",".join(str(v) for v in SWEDEN_BBOX)
    url = f"{API}/{key}/{source}/{bbox}/{n_days}/{start.isoformat()}"
    for attempt in range(4):
        try:
            response = client.get(url, timeout=60)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            if attempt == 3:
                # Do not chain the original error: its message contains the URL, and the URL
                # contains the API key.
                status = getattr(getattr(exc, "response", None), "status_code", "n/a")
                raise RuntimeError(f"FIRMS request failed: {source} {start} (HTTP {status})") from None
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download(
    start: date,
    end: date,
    sources: tuple[str, ...] = SOURCES,
    out_dir: Path = RAW_DIR,
) -> list[Path]:
    """Download raw detections for start..end. Returns the files written or already present."""
    key = get_key()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with httpx.Client() as client:
        for source in sources:
            for chunk_start, n in chunks(start, end):
                path = out_dir / f"{source}_{chunk_start.isoformat()}_{n}d.csv"
                paths.append(path)
                if path.exists():
                    continue
                text = fetch_chunk(client, key, source, chunk_start, n)
                if text.lstrip().lower().startswith(("invalid", "error", "<")):
                    raise RuntimeError(f"FIRMS returned an error for {source} {chunk_start}: {text[:100]}")
                path.write_text(text)
    return paths
