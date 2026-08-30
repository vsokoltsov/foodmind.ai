.PHONY: lint typecheck test-unit test-integration test

lint:
	uv run ruff check app tests

typecheck:
	uv run ty check app

test-unit:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

test:
	uv run pytest
