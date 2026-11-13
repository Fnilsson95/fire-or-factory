"""Command line entry point: `fof`. Subcommands are added during the weekend build."""

import argparse

from fof import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fof", description="Fire or Factory? pipeline")
    parser.add_argument("--version", action="version", version=f"fof {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
