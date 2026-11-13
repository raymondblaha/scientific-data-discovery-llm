"""Validation helpers for scientific metadata records."""

from __future__ import annotations

from datetime import date
from typing import Any


def _parse_iso_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def validate_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    for field in ("source", "source_identifier", "title", "description"):
        if not record.get(field):
            errors.append(f"missing required field: {field}")

    source_url = record.get("source_url") or record.get("landing_page")
    if not source_url:
        errors.append("missing required field: source_url")
    elif not str(source_url).startswith(("http://", "https://")):
        errors.append("source_url must be an absolute http(s) URL")

    for field in ("start_date", "end_date"):
        value = record.get(field)
        if value is not None and _parse_iso_date(value) is None:
            errors.append(f"invalid ISO date for {field}: {value!r}")

    if record.get("variables") is not None and not isinstance(record["variables"], list):
        errors.append("variables must be a list when present")
    if record.get("units") is not None and not isinstance(record["units"], list):
        errors.append("units must be a list when present")

    return (len(errors) == 0, errors)
