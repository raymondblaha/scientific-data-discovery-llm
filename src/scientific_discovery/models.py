"""Validated scientific dataset metadata models."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    landing_page: str = Field(..., min_length=1)
    keywords: list[str] = Field(..., min_length=1)
    publication_date: date | None = None
    license: str | None = None

    @field_validator("landing_page")
    @classmethod
    def validate_landing_page(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("landing_page must be an absolute http(s) URL")
        return value

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        normalized = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError("each keyword must be a string")
            cleaned = item.strip()
            if not cleaned:
                continue
            normalized.append(cleaned)
        if not normalized:
            raise ValueError("keywords must contain at least one non-empty value")
        return normalized

    @property
    def keyword_text(self) -> str:
        return " ".join(self.keywords)


class SourceDataset(BaseModel):
    source: str
    source_identifier: str
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    site_code: str | None = None
    site_name: str | None = None
    location: str | None = None
    variables: list[dict[str, Any]] | None = None
    units: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    acquisition_timestamp: str | None = None
    source_content_hash: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    synthetic: bool = False
