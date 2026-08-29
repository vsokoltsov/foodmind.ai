"""Validated Elasticsearch document models used by repositories."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.aggregates import (
    BrandedFood as BrandedFoodAggregate,
    FoundationFood as FoundationFoodAggregate,
    Nutrition,
    OpenFoodFactsProduct as OpenFoodFactsAggregate,
)
from app.clients.openfoodfacts.models import OpenFoodFactsProduct
from app.clients.usda_fdc.models import BrandedFood, FoodNutrient, FoundationFood


class NutritionDocument(BaseModel):
    """Flattened nutrient stored in USDA food indexes."""

    model_config = ConfigDict(frozen=True)

    id: int
    number: str
    name: str
    unit: str
    amount: float | None

    @classmethod
    def from_usda(cls, nutrient: FoodNutrient) -> "NutritionDocument":
        """Create an indexed nutrient from a USDA nutrient measurement."""
        return cls(
            id=nutrient.nutrient.id,
            number=nutrient.nutrient.number,
            name=nutrient.nutrient.name,
            unit=nutrient.nutrient.unit_name,
            amount=nutrient.amount,
        )

    @classmethod
    def from_domain(cls, nutrient: Nutrition) -> "NutritionDocument":
        """Create an indexed nutrient from a canonical nutrition object."""
        return cls.model_validate(nutrient.model_dump())


class FoundationDocument(BaseModel):
    """USDA Foundation Food document stored in Elasticsearch."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["usda_fdc"] = "usda_fdc"
    entity_type: Literal["foundation_food"] = "foundation_food"
    label: str
    description: str | None
    fdc_id: int
    category: str
    scientific_name: str | None
    publication_date: str
    nutrients: list[NutritionDocument]

    @classmethod
    def from_usda(cls, food: FoundationFood) -> "FoundationDocument":
        """Create an indexed document from a USDA Foundation Food."""
        return cls(
            id=f"usda-fdc:{food.fdc_id}",
            label=food.description,
            description=None,
            fdc_id=food.fdc_id,
            category=food.food_category.description,
            scientific_name=food.scientific_name,
            publication_date=food.publication_date,
            nutrients=[
                NutritionDocument.from_usda(nutrient)
                for nutrient in food.food_nutrients
            ],
        )

    @classmethod
    def from_domain(cls, food: FoundationFoodAggregate) -> "FoundationDocument":
        """Create an indexed document from a canonical Foundation Food."""
        return cls.model_validate(food.model_dump())


class BrandedDocument(BaseModel):
    """USDA Branded Food document stored in Elasticsearch."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["usda_fdc"] = "usda_fdc"
    entity_type: Literal["branded_food"] = "branded_food"
    label: str
    description: str | None
    fdc_id: int
    category: str
    brand_owner: str
    brand_name: str | None
    gtin_upc: str
    ingredients: str
    market_country: str
    publication_date: str
    serving_size: float
    serving_size_unit: str
    nutrients: list[NutritionDocument]

    @classmethod
    def from_usda(cls, food: BrandedFood) -> "BrandedDocument":
        """Create an indexed document from a USDA Branded Food."""
        return cls(
            id=f"usda-fdc:{food.fdc_id}",
            label=food.description,
            description=food.short_description,
            fdc_id=food.fdc_id,
            category=food.branded_food_category,
            brand_owner=food.brand_owner,
            brand_name=food.brand_name,
            gtin_upc=food.gtin_upc,
            ingredients=food.ingredients,
            market_country=food.market_country,
            publication_date=food.publication_date,
            serving_size=food.serving_size,
            serving_size_unit=food.serving_size_unit,
            nutrients=[
                NutritionDocument.from_usda(nutrient)
                for nutrient in food.food_nutrients
            ],
        )

    @classmethod
    def from_domain(cls, food: BrandedFoodAggregate) -> "BrandedDocument":
        """Create an indexed document from a canonical Branded Food."""
        return cls.model_validate(food.model_dump())


class OpenFoodFactsDocument(BaseModel):
    """Open Food Facts product document stored in Elasticsearch."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: Literal["openfoodfacts"] = "openfoodfacts"
    entity_type: Literal["product"] = "product"
    label: str
    description: str | None
    code: str
    brands: str | None
    brands_tags: list[str]
    categories: str | None
    categories_tags: list[str]
    countries: str | None
    countries_tags: list[str]
    ingredients: str | None
    ingredients_tags: list[str]
    allergens: str | None
    allergens_tags: list[str]
    traces: str | None
    traces_tags: list[str]
    labels_tags: list[str]
    quantity: str | None
    serving_size: str | None
    nutrition_grade: str | None
    nova_group: int | None
    nutriments: dict[str, int | float | str | None]
    image_url: str | None
    image_front_url: str | None
    last_modified_at: int | None

    @classmethod
    def from_open_food_facts(
        cls,
        product: OpenFoodFactsProduct,
    ) -> "OpenFoodFactsDocument":
        """Create an indexed document from an Open Food Facts product."""
        return cls(
            id=f"openfoodfacts:{product.code}",
            label=product.product_name or product.generic_name or product.code,
            description=product.generic_name,
            code=product.code,
            brands=product.brands,
            brands_tags=product.brands_tags,
            categories=product.categories,
            categories_tags=product.categories_tags,
            countries=product.countries,
            countries_tags=product.countries_tags,
            ingredients=product.ingredients_text,
            ingredients_tags=product.ingredients_tags,
            allergens=product.allergens,
            allergens_tags=product.allergens_tags,
            traces=product.traces,
            traces_tags=product.traces_tags,
            labels_tags=product.labels_tags,
            quantity=product.quantity,
            serving_size=product.serving_size,
            nutrition_grade=product.nutrition_grades,
            nova_group=product.nova_group,
            nutriments=product.nutriments,
            image_url=product.image_url,
            image_front_url=product.image_front_url,
            last_modified_at=product.last_modified_t,
        )

    @classmethod
    def from_domain(cls, product: OpenFoodFactsAggregate) -> "OpenFoodFactsDocument":
        """Create an indexed document from a canonical product object."""
        return cls.model_validate(product.model_dump())
