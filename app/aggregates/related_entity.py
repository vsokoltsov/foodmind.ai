"""Related Wikidata business object."""

from pydantic import BaseModel, ConfigDict


class RelatedEntity(BaseModel):
    """A Wikidata entity referenced by a food entity."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str | None = None
