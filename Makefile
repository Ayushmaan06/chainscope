.PHONY: install lint format typecheck test check contracts-build contracts-test

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

contracts-build:
	cd contracts && forge build

contracts-test:
	cd contracts && forge test

check: lint format typecheck test contracts-build contracts-test
