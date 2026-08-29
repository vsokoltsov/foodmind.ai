from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.aggregates.openfoodfacts_product import (
    OpenFoodFactsProduct as OpenFoodFactsAggregate,
)


class DownloadArtifact(BaseModel):
    """Metadata describing a downloaded Open Food Facts export."""

    model_config = ConfigDict(frozen=True)

    source_url: str
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OpenFoodFactsProduct(BaseModel):
    """MVP fields read from one Open Food Facts JSON Lines record.

    Open Food Facts records contain many generated and evolving fields. Unknown
    fields are intentionally ignored so the streaming reader remains compatible
    with newer exports while validating the fields used by FoodMind.
    """

    model_config = ConfigDict(extra="ignore")

    code: str
    product_name: str | None = None
    generic_name: str | None = None
    brands: str | None = None
    brands_tags: list[str] = Field(default_factory=list)
    categories: str | None = None
    categories_tags: list[str] = Field(default_factory=list)
    countries: str | None = None
    countries_tags: list[str] = Field(default_factory=list)
    ingredients_text: str | None = None
    ingredients_tags: list[str] = Field(default_factory=list)
    allergens: str | None = None
    allergens_tags: list[str] = Field(default_factory=list)
    traces: str | None = None
    traces_tags: list[str] = Field(default_factory=list)
    labels_tags: list[str] = Field(default_factory=list)
    quantity: str | None = None
    serving_size: str | None = None
    nutrition_grades: str | None = None
    nova_group: int | None = None
    nutriments: dict[str, int | float | str | None] = Field(default_factory=dict)
    image_url: str | None = None
    image_front_url: str | None = None
    last_modified_t: int | None = None

    def to_domain(self) -> OpenFoodFactsAggregate:
        """Convert the source-shaped product into a canonical product object."""
        return OpenFoodFactsAggregate(
            id=f"openfoodfacts:{self.code}",
            label=self.product_name or self.generic_name or self.code,
            description=self.generic_name,
            code=self.code,
            brands=self.brands,
            brands_tags=self.brands_tags,
            categories=self.categories,
            categories_tags=self.categories_tags,
            countries=self.countries,
            countries_tags=self.countries_tags,
            ingredients=self.ingredients_text,
            ingredients_tags=self.ingredients_tags,
            allergens=self.allergens,
            allergens_tags=self.allergens_tags,
            traces=self.traces,
            traces_tags=self.traces_tags,
            labels_tags=self.labels_tags,
            quantity=self.quantity,
            serving_size=self.serving_size,
            nutrition_grade=self.nutrition_grades,
            nova_group=self.nova_group,
            nutriments=self.nutriments,
            image_url=self.image_url,
            image_front_url=self.image_front_url,
            last_modified_at=self.last_modified_t,
        )
