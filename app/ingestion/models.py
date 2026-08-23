"""Normalized models emitted by ingestion pipelines."""

from pydantic import BaseModel, Field


class RelatedEntity(BaseModel):
    """A Wikidata entity referenced by a normalized food record."""

    id: str
    label: str | None = None


class WikidataEntityRecord(BaseModel):
    """A staged base entity row returned by Wikidata."""

    id: str
    label: str
    description: str | None = None


class WikidataAliasRecord(BaseModel):
    """A staged Wikidata alias row."""

    item_id: str
    alias: str


class WikidataTaxonomyRecord(BaseModel):
    """A staged Wikidata taxonomy row."""

    item_id: str
    instance_id: str | None = None
    instance_label: str | None = None
    subclass_id: str | None = None
    subclass_label: str | None = None


class WikidataOriginRecord(BaseModel):
    """A staged Wikidata country-of-origin and cuisine row."""

    item_id: str
    country_id: str | None = None
    country_label: str | None = None
    cuisine_id: str | None = None
    cuisine_label: str | None = None


class WikidataMediaArticleRecord(BaseModel):
    """A staged Wikidata image and article row."""

    item_id: str
    image: str | None = None
    article: str | None = None


class FoodEntityRecord(BaseModel):
    """A normalized food entity assembled from Wikidata query responses."""

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
