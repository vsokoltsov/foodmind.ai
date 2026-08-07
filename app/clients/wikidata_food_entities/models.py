from pydantic import BaseModel, ConfigDict, Field


class WikidataValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    value: str
    xml_lang: str | None = Field(default=None, alias="xml:lang")

    @property
    def qid_from_uri(self) -> str:
        return self.value.rsplit("/", 1)[-1]


class WikidataFoodEntityBinding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item: WikidataValue
    item_label: WikidataValue = Field(alias="itemLabel")
    item_description: WikidataValue | None = Field(
        default=None,
        alias="itemDescription",
    )


class WikidataResults(BaseModel):
    bindings: list[WikidataFoodEntityBinding]

    @property
    def qids(self) -> list[str]:
        qids = [
            row.item.qid_from_uri
            for row in self.bindings
            if row.item.type == "uri"
        ]
        return [f"wd:{qid}" for qid in qids]


class WikiDataResponse(BaseModel):
    results: WikidataResults


class WikidataFoodEntityAliasBinding(BaseModel):
    item: WikidataValue
    alias: WikidataValue


class WikidataAliasResults(BaseModel):
    bindings: list[WikidataFoodEntityAliasBinding]


class WikiDataAliasResponse(BaseModel):
    results: WikidataAliasResults


class WikidataTaxonomyBinding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item: WikidataValue
    instance: WikidataValue | None = None
    instance_label: WikidataValue | None = Field(default=None, alias="instanceLabel")
    subclass: WikidataValue | None = None
    subclass_label: WikidataValue | None = Field(default=None, alias="subclassLabel")


class WikidataTaxonomyResults(BaseModel):
    bindings: list[WikidataTaxonomyBinding]


class WikidataTaxonomyResponse(BaseModel):
    results: WikidataTaxonomyResults


class WikidataOriginalCuisineBinding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item: WikidataValue
    country: WikidataValue | None = None
    country_label: WikidataValue | None = Field(default=None, alias="countryLabel")
    cuisine: WikidataValue | None = None
    cuisine_label: WikidataValue | None = Field(default=None, alias="cuisineLabel")


class WikidataOriginalCuisineResults(BaseModel):
    bindings: list[WikidataOriginalCuisineBinding]


class WikidataOriginalCuisineResponse(BaseModel):
    results: WikidataOriginalCuisineResults


class WikidataMediaArticleBinding(BaseModel):
    item: WikidataValue
    image: WikidataValue | None = None
    article: WikidataValue | None = None


class WikidataMediaArticleResults(BaseModel):
    bindings: list[WikidataMediaArticleBinding]


class WikidataMediaArticlesResponse(BaseModel):
    results: WikidataMediaArticleResults
