"""Pydantic models for USDA FoodData Central JSON downloads."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DownloadArtifact(BaseModel):
    """Metadata describing an archive downloaded from FoodData Central."""

    model_config = ConfigDict(frozen=True)

    source_url: str
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class USDAFoodDataModel(BaseModel):
    """Base model for FoodData Central's camel-cased JSON fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FoodCategory(USDAFoodDataModel):
    """USDA food category metadata."""

    id: int | None = None
    code: str | None = None
    description: str


class Nutrient(USDAFoodDataModel):
    """Definition and unit of a nutrient measured by FoodData Central."""

    id: int
    number: str
    name: str
    rank: int | None = None
    unit_name: str


class FoodNutrientSource(USDAFoodDataModel):
    """Source from which a food nutrient value was obtained."""

    id: int | None = None
    code: str | None = None
    description: str | None = None


class FoodNutrientDerivation(USDAFoodDataModel):
    """Method used to derive a food nutrient value."""

    code: str | None = None
    description: str | None = None
    food_nutrient_source: FoodNutrientSource = Field(
        default_factory=FoodNutrientSource
    )


class FoodNutrient(USDAFoodDataModel):
    """A nutrient measurement attached to a USDA food record."""

    type: str
    id: int
    nutrient: Nutrient
    amount: float | None = None
    data_points: int | None = None
    min: float | None = None
    max: float | None = None
    median: float | None = None
    footnote: str | None = None
    food_nutrient_derivation: FoodNutrientDerivation | None = None


class FoodAttributeType(USDAFoodDataModel):
    """Definition of a USDA food attribute."""

    id: int
    name: str | None = None
    description: str | None = None


class FoodAttribute(USDAFoodDataModel):
    """Additional metadata associated with a USDA food record."""

    id: int
    name: str | None = None
    value: str | None = None
    food_attribute_type: FoodAttributeType | None = None


class MeasureUnit(USDAFoodDataModel):
    """Unit used to describe a food portion."""

    id: int
    name: str
    abbreviation: str


class FoodPortion(USDAFoodDataModel):
    """A household or measured portion and its gram weight."""

    id: int
    amount: float
    gram_weight: float
    measure_unit: MeasureUnit
    sequence_number: int
    modifier: str | None = None
    min_year_acquired: int | None = None
    portion_description: str | None = None
    value: float | None = None


class InputFoodReference(USDAFoodDataModel):
    """Food record referenced by a Foundation Food input sample."""

    fdc_id: int
    data_type: str
    description: str
    food_class: str
    publication_date: str
    food_category: FoodCategory


class InputFood(USDAFoodDataModel):
    """Input sample used to calculate a Foundation Food record."""

    id: int
    food_description: str
    input_food: InputFoodReference


class NutrientConversionFactor(USDAFoodDataModel):
    """Calorie or protein conversion factor for a Foundation Food."""

    type: str
    value: float | None = None
    protein_value: float | None = None
    fat_value: float | None = None
    carbohydrate_value: float | None = None
    nitrogen_value: float | None = None


class FoundationFood(USDAFoodDataModel):
    """A food record from the FoodData Central Foundation Foods export."""

    food_class: str
    description: str
    food_nutrients: list[FoodNutrient]
    food_attributes: list[FoodAttribute]
    food_category: FoodCategory
    is_historical_reference: bool
    ndb_number: int
    data_type: str
    fdc_id: int
    publication_date: str
    scientific_name: str | None = None
    food_portions: list[FoodPortion] = Field(default_factory=list)
    input_foods: list[InputFood] = Field(default_factory=list)
    nutrient_conversion_factors: list[NutrientConversionFactor] = Field(
        default_factory=list
    )


class FoundationFoodsResponse(USDAFoodDataModel):
    """Top-level object in a Foundation Foods JSON download.

    The April 2026 USDA file contains trailing JSON ``null`` entries, so the
    collection explicitly accepts them rather than rejecting the whole export.
    """

    foundation_foods: list[FoundationFood | None] = Field(alias="FoundationFoods")

    @property
    def foods(self) -> list[FoundationFood]:
        """Return actual food records without the export's null placeholders."""
        return [food for food in self.foundation_foods if food is not None]


class LabelNutrientValue(USDAFoodDataModel):
    """Nutrient value printed on a branded product label."""

    value: float


class LabelNutrients(USDAFoodDataModel):
    """Nutrition Facts values supplied for a branded product."""

    calories: LabelNutrientValue | None = None
    fat: LabelNutrientValue | None = None
    saturated_fat: LabelNutrientValue | None = None
    trans_fat: LabelNutrientValue | None = None
    cholesterol: LabelNutrientValue | None = None
    sodium: LabelNutrientValue | None = None
    carbohydrates: LabelNutrientValue | None = None
    fiber: LabelNutrientValue | None = None
    sugars: LabelNutrientValue | None = None
    added_sugar: LabelNutrientValue | None = None
    protein: LabelNutrientValue | None = None
    vitamin_d: LabelNutrientValue | None = None
    calcium: LabelNutrientValue | None = None
    iron: LabelNutrientValue | None = None
    potassium: LabelNutrientValue | None = None


class BrandedFoodUpdate(USDAFoodDataModel):
    """Historical entry embedded in a branded food's update log."""

    fdc_id: int
    food_class: str
    data_type: str
    description: str
    publication_date: str
    food_attributes: list[FoodAttribute] = Field(default_factory=list)
    brand_owner: str | None = None
    brand_name: str | None = None
    subbrand_name: str | None = None
    gtin_upc: str | None = None
    ingredients: str | None = None
    serving_size: float | None = None
    serving_size_unit: str | None = None
    household_serving_full_text: str | None = None
    branded_food_category: str | None = None
    data_source: str | None = None
    package_weight: str | None = None
    modified_date: str | None = None
    available_date: str | None = None
    market_country: str | None = None


class BrandedFood(USDAFoodDataModel):
    """A product from the FoodData Central Branded Foods export."""

    food_class: str
    description: str
    food_nutrients: list[FoodNutrient]
    food_attributes: list[FoodAttribute]
    modified_date: str
    available_date: str
    market_country: str
    brand_owner: str
    brand_name: str | None = None
    subbrand_name: str | None = None
    data_source: str
    branded_food_category: str
    gtin_upc: str
    ingredients: str
    serving_size: float
    serving_size_unit: str
    household_serving_full_text: str
    label_nutrients: LabelNutrients
    trade_channels: list[str]
    microbes: list[dict[str, object]]
    food_update_log: list[BrandedFoodUpdate]
    data_type: str
    fdc_id: int
    publication_date: str
    package_weight: str | None = None
    short_description: str | None = None


class BrandedFoodsResponse(USDAFoodDataModel):
    """Top-level object in a Branded Foods JSON download."""

    branded_foods: list[BrandedFood] = Field(alias="BrandedFoods")
