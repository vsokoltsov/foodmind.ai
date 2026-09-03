.PHONY: lint typecheck test-unit test-integration evaluation evaluation-retrieval evaluation-food-search evaluation-nutrition-analysis evaluation-product-comparison evaluation-food-recommendation evaluation-orchestrator evaluation-planner evaluation-executor test

lint:
	uv run ruff check app tests

typecheck:
	uv run ty check app

test-unit:
	uv run pytest -m "not integration and not evaluation"

test-integration:
	uv run pytest -m "integration and not evaluation"

evaluation-food-search:
	uv run pytest -m evaluation tests/evaluation/test_food_search.py -q

evaluation-retrieval:
	uv run pytest -m evaluation tests/evaluation/test_retrieval.py -q

evaluation-nutrition-analysis:
	uv run pytest -m evaluation tests/evaluation/test_nutrition_analysis.py -q

evaluation-product-comparison:
	uv run pytest -m evaluation tests/evaluation/test_product_comparison.py -q

evaluation-food-recommendation:
	uv run pytest -m evaluation tests/evaluation/test_food_recommendation.py -q

evaluation-orchestrator:
	uv run pytest -m evaluation tests/evaluation/test_orchestrator.py -q

evaluation-planner:
	uv run pytest -m evaluation tests/evaluation/test_planner.py -q

evaluation-executor:
	uv run pytest -m evaluation tests/evaluation/test_executor.py -q

evaluation: evaluation-retrieval evaluation-food-search evaluation-nutrition-analysis evaluation-product-comparison evaluation-food-recommendation evaluation-orchestrator evaluation-planner evaluation-executor

test:
	$(MAKE) test-unit test-integration
