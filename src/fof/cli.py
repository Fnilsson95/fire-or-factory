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
"""

import argparse
from datetime import date

from fof import __version__, ingest

# argument vector
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fof", description="Fire or Factory? pipeline")
    parser.add_argument("--version", action="version", version=f"fof {__version__}")
    sub = parser.add_subparsers(dest="command")

    ing = sub.add_parser("ingest", help="download raw FIRMS detections for Sweden")
    ing.add_argument("--start", required=True, type=date.fromisoformat)
    ing.add_argument("--end", required=True, type=date.fromisoformat)
    ing.add_argument("--sources", nargs="+", default=list(ingest.SOURCES))

    args = parser.parse_args(argv)
    if args.command == "ingest":
        paths = ingest.download(args.start, args.end, tuple(args.sources))
        print(f"{len(paths)} raw files in {ingest.RAW_DIR}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
