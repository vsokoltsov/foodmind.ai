"""Validated Elasticsearch document models used by repositories."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

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
