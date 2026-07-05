.PHONY: install-dev test lint validate

install-dev:
	uv sync --extra dev

test:
	uv run python -m pytest -q

lint:
	uv run python -m ruff check .

validate: install-dev
	uv run python -m pytest -q
	uv run python -m ruff check .
