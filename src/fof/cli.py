"""Command line entry point: "fof" """

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
