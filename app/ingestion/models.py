"""Transport models used by the Wikidata extraction stages."""

from pydantic import BaseModel

from app.aggregates import FoodEntity, RelatedEntity

# Kept as a compatibility name for staged dlt tables and existing integrations.
FoodEntityRecord = FoodEntity


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
