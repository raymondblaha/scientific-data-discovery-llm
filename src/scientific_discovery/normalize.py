"""Normalization helpers for heterogeneous scientific metadata formats."""

from __future__ import annotations

from typing import Any


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or "unknown")
    source_identifier = str(raw.get("source_identifier") or raw.get("id") or raw.get("dataset_id") or "unknown")
    title = raw.get("title") or raw.get("dataset_name") or raw.get("name") or source_identifier
    description = raw.get("description") or raw.get("dataset_description") or ""
    source_url = raw.get("source_url") or raw.get("landing_page") or raw.get("url") or ""
    site_code = raw.get("site_code") or raw.get("siteCode")
    site_name = raw.get("site_name") or raw.get("siteName") or raw.get("site")
    location = raw.get("location") or raw.get("geo")
    variables = raw.get("variables") if isinstance(raw.get("variables"), list) else []
    units = raw.get("units") if isinstance(raw.get("units"), list) else []
    start_date = raw.get("start_date") or raw.get("calendar_start") or raw.get("begin_date")
    end_date = raw.get("end_date") or raw.get("calendar_end") or raw.get("finish_date")
    keywords = raw.get("keywords") if isinstance(raw.get("keywords"), list) else []

    return {
        "dataset_id": source_identifier,
        "source": source,
        "source_identifier": source_identifier,
        "title": str(title),
        "description": str(description),
        "source_url": str(source_url) if source_url else "",
        "landing_page": str(source_url) if source_url else "",
        "site_code": site_code,
        "site_name": site_name,
        "location": location,
        "variables": variables,
        "units": units,
        "start_date": start_date,
        "end_date": end_date,
        "raw_metadata": dict(raw),
        "synthetic": bool(raw.get("synthetic", False)),
        "keywords": keywords,
    }
