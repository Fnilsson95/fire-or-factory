.PHONY: setup test lint app all

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

app:
	uv run streamlit run app/streamlit_app.py

# Raw files to app-ready data. Wired up during the weekend build.
all:
	@echo "pipeline not implemented yet"
