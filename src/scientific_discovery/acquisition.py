"""Public metadata acquisition helpers."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen


def fetch_arm_metadata(limit: int = 10) -> list[dict]:
    url = f"https://adc.arm.gov/elastic/metadata/_search?size={max(1, min(limit, 1000))}&q=*:*"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "scientific-data-discovery/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", {}).get("hits", [])
    records: list[dict] = []
    for hit in hits:
        source = hit.get("_source") or {}
        record = dict(source)
        record.setdefault("source", "arm")
        record.setdefault("source_identifier", hit.get("_id"))
        record.setdefault("source_url", "https://adc.arm.gov/discovery/")
        record.setdefault("synthetic", False)
        records.append(record)
    return records
