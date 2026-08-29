"""Canonical Wikidata food entity."""

from pydantic import BaseModel, ConfigDict, Field

from app.aggregates.related_entity import RelatedEntity


class FoodEntity(BaseModel):
    """Canonical food concept assembled from Wikidata data."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    countries: list[RelatedEntity] = Field(default_factory=list)
    cuisines: list[RelatedEntity] = Field(default_factory=list)
    instance_of: list[RelatedEntity] = Field(default_factory=list)
    subclasses: list[RelatedEntity] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    articles: list[str] = Field(default_factory=list)
