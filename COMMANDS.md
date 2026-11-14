# Commands

All commands run from the repo root.

## Setup

```bash
uv sync                  # install dependencies into .venv
```

Create a `.env` file in the repo root with your FIRMS key:

```
FIRMS_MAP_KEY="your-key-here"
```

`.env` is gitignored. Never commit it.

## Make targets

| Command      | What it does                                      |
| ------------ | ------------------------------------------------- |
| `make setup` | Install dependencies (`uv sync`)                  |
| `make test`  | Run the tests (`pytest`)                          |
| `make lint`  | Check code style (`ruff`)                         |
| `make app`   | Start the Streamlit app                           |
| `make all`   | Full pipeline, raw to app-ready. Not wired up yet |

## Pipeline: `fof`

```bash
uv run fof --help        # list commands
uv run fof --version     # print the version
uv run fof <command> --help
```

### `fof ingest`

Downloads raw FIRMS detections for Sweden into `data/raw/`, one CSV per source and 5-day chunk.
Existing files are skipped, so an interrupted run can simply be restarted.

| Option      | Required | Meaning                                                                            |
| ----------- | -------- | ---------------------------------------------------------------------------------- |
| `--start`   | yes      | First date, `YYYY-MM-DD`                                                           |
| `--end`     | yes      | Last date, `YYYY-MM-DD`, inclusive                                                 |
| `--sources` | no       | One or more of `MODIS_SP`, `VIIRS_SNPP_SP`, `VIIRS_NOAA20_SP` (default: all three) |

Examples:

```bash
uv run fof ingest --start 2018-07-01 --end 2018-07-31
uv run fof ingest --start 2018-01-01 --end 2018-12-31 --sources MODIS_SP
```

Archive coverage per source: `MODIS_SP` from 2000-11, `VIIRS_SNPP_SP` from 2012-01, `VIIRS_NOAA20_SP` from 2018-04.

<!-- Add a section for each new command: normalise, features, model, calendar -->
