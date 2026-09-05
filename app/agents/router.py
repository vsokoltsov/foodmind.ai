"""Low-latency deterministic routing for FoodMind requests."""

from dataclasses import dataclass
from enum import StrEnum

from app.agents.planner import AgentName


class RouteKind(StrEnum):
    """Execution paths available before planning a workflow."""

    DIRECT = "direct"
    PLANNED = "planned"


@dataclass(frozen=True)
class Route:
    """A selected request execution path."""

    kind: RouteKind
    agent: AgentName | None = None


@dataclass(frozen=True)
class FoodMindRouter:
    """Route obvious single-agent requests without an LLM classification call."""

    def route(self, prompt: str) -> Route:
        """Select a specialist for clear intents or planning for ambiguous ones."""
        text = prompt.casefold()
        if self._contains(text, "compare", " versus ", " vs ", "difference between"):
            return Route(RouteKind.DIRECT, AgentName.PRODUCT_COMPARISON)
        if self._contains(
            text,
            "recommend",
            "suggest",
            "avoid ",
            "allergen",
            "dietary",
            "vegan",
            "vegetarian",
        ):
            return Route(RouteKind.DIRECT, AgentName.FOOD_RECOMMENDATION)
        if self._contains(
            text,
            "calorie",
            "protein",
            "fiber",
            "nutrient",
            "nutrition",
            "carbohydrate",
            "fat",
        ):
            return Route(RouteKind.DIRECT, AgentName.NUTRITION_ANALYSIS)
        if self._contains(text, "find", "search", "cuisine", "country", "category", "brand"):
            return Route(RouteKind.DIRECT, AgentName.FOOD_SEARCH)
        return Route(RouteKind.PLANNED)

    @staticmethod
    def _contains(text: str, *terms: str) -> bool:
        """Return whether a request contains one of the routing terms."""
        return any(term in text for term in terms)
