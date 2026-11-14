"""Validation and ingestion utilities for scientific metadata records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from pydantic import ValidationError

from .models import Dataset, SourceDataset


@dataclass
class ValidationResult:
    records: list[Dataset | SourceDataset]
    errors: list[dict]


def validate_jsonl(path: Path) -> ValidationResult:
    records: list[Dataset | SourceDataset] = []
    errors: list[dict] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise TypeError("each JSONL entry must be an object")

                if "dataset_id" in payload:
                    record = Dataset.model_validate(payload)
                    dataset_id = record.dataset_id
                else:
                    record = SourceDataset.model_validate(payload)
                    dataset_id = record.source_identifier

                if dataset_id in seen:
                    raise ValueError(f"duplicate dataset_id: {dataset_id}")
                seen.add(dataset_id)
                records.append(record)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                errors.append({"line": line_number, "error": str(exc)})
    return ValidationResult(records=records, errors=errors)


def fetch_arm_metadata(limit: int = 10) -> list[dict]:
    url = f"https://adc.arm.gov/elastic/metadata/_search?size={max(1, min(limit, 1000))}&q=*:*"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "scientific-data-discovery/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", {}).get("hits", [])
    rows: list[dict] = []
    for hit in hits:
        source = hit.get("_source") or {}
        row = dict(source)
        row.setdefault("source", "arm")
        row.setdefault("source_identifier", hit.get("_id"))
        row.setdefault("source_url", "https://adc.arm.gov/discovery/")
        row.setdefault("synthetic", False)
        rows.append(row)
    return rows


def normalize_arm_record(raw: dict) -> SourceDataset:
    record = SourceDataset(
        source=str(raw.get("source") or "arm"),
        source_identifier=str(raw.get("source_identifier") or raw.get("_id") or raw.get("id") or "unknown"),
        title=(raw.get("title") or raw.get("dataset_name") or raw.get("instrument_class_name_text") or raw.get("name") or raw.get("source_identifier")),
        description=(raw.get("description") or raw.get("primary_meas_type_desc") or raw.get("meas_subcategory_description") or raw.get("dataset_description") or ""),
        source_url=(raw.get("source_url") or raw.get("dataset_url") or raw.get("link") or raw.get("url") or "https://adc.arm.gov/discovery/"),
        site_code=(raw.get("site_code") or raw.get("site") or raw.get("siteCode")),
        site_name=(raw.get("site_name") or raw.get("siteName") or raw.get("site") or raw.get("site_name_text")),
        location=(raw.get("location") or raw.get("geo") or raw.get("site_name")),
        variables=(raw.get("variables") if isinstance(raw.get("variables"), list) else []),
        units=(raw.get("units") if isinstance(raw.get("units"), list) else []),
        start_date=(raw.get("start_date") or raw.get("monitor_start") or raw.get("begin_date") or raw.get("calendar_start")),
        end_date=(raw.get("end_date") or raw.get("monitor_end") or raw.get("end_date") or raw.get("calendar_end")),
        acquisition_timestamp=raw.get("acquisition_timestamp"),
        source_content_hash=raw.get("source_content_hash"),
        raw_metadata=raw,
        synthetic=bool(raw.get("synthetic", False)),
    )
    return record
