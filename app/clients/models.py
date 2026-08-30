from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RAW_DATA_DIR = Path("data/raw")
USER_AGENT = "foodmind-ai/0.1 (portfolio data ingestion; contact: local-dev)"


RetrievalStrategy = Literal[
    "direct",
    "html_link",
    "json_api",
    "sparql",
    "wikibooks_export"
]


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["success"] = "success"
    source_id: str
    source_name: str
    source_url: str
    license: str
    destination: str
    bytes_written: int
    sha256: str
    retrieved_at: str


class RetrievalFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["failed"] = "failed"
    source_id: str
    source_name: str
    error: str
    retrieved_at: str


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    license: str
    version: str
    strategy: RetrievalStrategy
    destination: str
    url: str | None = None
    page_url: str | None = None
    href_contains: tuple[str, ...] = Field(default_factory=tuple)
    link_text_contains: tuple[str, ...] = Field(default_factory=tuple)
    sparql_query: str | None = None
    referer: str | None = None
    params: dict[str, str] = Field(default_factory=dict)

    @property
    def output_path(self) -> Path:
        return RAW_DATA_DIR / self.id / self.version / self.destination
