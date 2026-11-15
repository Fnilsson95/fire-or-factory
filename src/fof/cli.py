"""Command line entry point: "fof"

Run from the repo root (FIRMS_MAP_KEY must be set in .env file)

    * uv run fof --help                 (list commands)
    * uv run fof --version              (print the version)
    * uv run fof ingest --help          (options for a command)

ingest --> Download raw FIRMS detections for Sweden into data/raw/
           uv run fof ingest --start 2018-07-01 --end 2018-07-31
           uv run fof ingest --start 2018-01-01 --end 2018-12-31 --sources MODIS_SP

    -- start (first date REQUIRED)
    -- end (last date REQUIRED)
    --sources MODIS_SP, VIIRS_SNPP_SP, VIIRS_NOAA20_SP (default: all three)

normalise --> Harmonises all raw files into one validated table "data/clean/detections.parquet"
              Same column names for both MODIS and VIIRS

              uv run fof normalise
"""

import argparse
from datetime import date

from fof import __version__, export, features, fire_calendar, ingest, model, normalise



# argument vector
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fof", description="Fire or Factory? pipeline")
    parser.add_argument("--version", action="version", version=f"fof {__version__}")
    sub = parser.add_subparsers(dest="command")

    ing = sub.add_parser("ingest", help="download raw FIRMS detections for Sweden")
    ing.add_argument("--start", required=True, type=date.fromisoformat)
    ing.add_argument("--end", required=True, type=date.fromisoformat)
    ing.add_argument("--sources", nargs="+", default=list(ingest.SOURCES))
    sub.add_parser("normalise", help="harmonise raw files into data/clean/detections.parquet")
    sub.add_parser("features", help="add grid-cell and detection features -> features.parquet")
    sub.add_parser("classify", help="rule baseline + classifier -> classified.parquet")
    sub.add_parser("calendar", help="fire-days per year and month -> fire_calendar.csv")
    sub.add_parser("export", help="write slim app data to app/data/ (commited)")

    args = parser.parse_args(argv)
    if args.command == "ingest":
        paths = ingest.download(args.start, args.end, tuple(args.sources))
        print(f"{len(paths)} raw files in {ingest.RAW_DIR}")
        return 0

    if args.command == "normalise":
        normalise.normalise()
        return 0

    if args.command == "features":
        features.build_features()
        return 0

    if args.command == "classify":
        df = model.classify()
        print("\nTop disagreements with FIRMS (check these on a map):")
        print(model.disagreements(df).to_string())
        return 0

    if args.command == "calendar":
        cal = fire_calendar.build_calendar()
        print("\nFire-days per month, both sensors, our cleaning:")
        print(fire_calendar.month_grid(cal).to_string())
        return 0

    if args.command == "export":
        export.export_app_data()
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
