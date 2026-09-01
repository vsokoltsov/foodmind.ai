.PHONY: lint typecheck test-unit test-integration evaluation test

lint:
	uv run ruff check app tests

typecheck:
	uv run ty check app

test-unit:
	uv run pytest -m "not integration and not evaluation"

test-integration:
	uv run pytest -m "integration and not evaluation"

evaluation:
	uv run pytest -m evaluation

test:
	$(MAKE) test-unit test-integration
