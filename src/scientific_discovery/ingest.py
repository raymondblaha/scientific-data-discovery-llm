"""Validate JSONL records; report invalid rows without dropping errors silently."""
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .models import Dataset


@dataclass
class ValidationResult:
    records: list[Dataset]
    errors: list[dict]


def validate_jsonl(path: Path) -> ValidationResult:
    records: list[Dataset] = []
    errors: list[dict] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
                record = Dataset.model_validate(payload)
                if record.dataset_id in seen:
                    raise ValueError(f"duplicate dataset_id: {record.dataset_id}")
                seen.add(record.dataset_id)
                records.append(record)
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                errors.append({"line": line_number, "error": str(exc)})
    return ValidationResult(records=records, errors=errors)
