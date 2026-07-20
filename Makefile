.PHONY: install lint format typecheck test check

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run black --check .

typecheck:
	uv run mypy src

test:
	uv run pytest

check: lint format typecheck test
