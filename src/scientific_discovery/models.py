"""Validated, source-agnostic scientific dataset metadata."""
from datetime import date
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: NonEmpty
    title: NonEmpty
    description: NonEmpty
    source: NonEmpty
    landing_page: HttpUrl
    keywords: list[NonEmpty] = Field(min_length=1)
    publication_date: date | None = None
    license: str | None = None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip().lower() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("keywords must contain nonempty terms")
        return normalized

    @model_validator(mode="after")
    def check_id(self) -> "Dataset":
        if len(self.dataset_id) > 200:
            raise ValueError("dataset_id must not exceed 200 characters")
        return self
