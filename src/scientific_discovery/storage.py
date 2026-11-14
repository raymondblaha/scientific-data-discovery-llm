"""PostgreSQL storage helpers for imported metadata records."""

from __future__ import annotations

import json
from typing import Any

import psycopg

from .normalize import normalize_record
from .validate import validate_record


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS dataset_records")
        cur.execute(
            """
            CREATE TABLE dataset_records (
                dataset_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_identifier TEXT UNIQUE,
                title TEXT,
                description TEXT,
                source_url TEXT,
                landing_page TEXT,
                site_code TEXT,
                site_name TEXT,
                location TEXT,
                variables JSONB,
                units JSONB,
                start_date DATE,
                end_date DATE,
                keywords JSONB,
                raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                date_status TEXT,
                synthetic BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def import_records(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> list[str]:
    inserted: list[str] = []
    with conn.cursor() as cur:
        for raw in rows:
            ok, _ = validate_record(raw)
            if not ok:
                continue
            normalized = normalize_record(raw)
            dataset_id = str(normalized["dataset_id"])
            source_identifier = str(normalized["source_identifier"])
            keywords = normalized.get("keywords") or []
            if not keywords:
                combined = " ".join(filter(None, [normalized.get("title"), normalized.get("description")]))
                keywords = combined.lower().split()
            date_status = "unknown"
            body = {
                "dataset_id": dataset_id,
                "source": normalized["source"],
                "source_identifier": source_identifier,
                "title": normalized["title"],
                "description": normalized["description"],
                "source_url": normalized["source_url"],
                "landing_page": normalized["landing_page"],
                "site_code": normalized.get("site_code"),
                "site_name": normalized.get("site_name"),
                "location": normalized.get("location"),
                "variables": json.dumps(normalized.get("variables") or []),
                "units": json.dumps(normalized.get("units") or []),
                "start_date": normalized.get("start_date"),
                "end_date": normalized.get("end_date"),
                "keywords": json.dumps(keywords),
                "raw_metadata": json.dumps(normalized.get("raw_metadata") or {}),
                "date_status": date_status,
                "synthetic": bool(normalized.get("synthetic", False)),
            }
            cur.execute(
                """
                INSERT INTO dataset_records (
                    dataset_id, source, source_identifier, title, description,
                    source_url, landing_page, site_code, site_name, location,
                    variables, units, start_date, end_date, keywords,
                    raw_metadata, date_status, synthetic, updated_at
                ) VALUES (
                    %(dataset_id)s, %(source)s, %(source_identifier)s, %(title)s,
                    %(description)s, %(source_url)s, %(landing_page)s,
                    %(site_code)s, %(site_name)s, %(location)s,
                    %(variables)s::jsonb, %(units)s::jsonb, %(start_date)s::date,
                    %(end_date)s::date, %(keywords)s::jsonb, %(raw_metadata)s::jsonb,
                    %(date_status)s, %(synthetic)s, NOW()
                ) ON CONFLICT (dataset_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    source_identifier = EXCLUDED.source_identifier,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    source_url = EXCLUDED.source_url,
                    landing_page = EXCLUDED.landing_page,
                    site_code = EXCLUDED.site_code,
                    site_name = EXCLUDED.site_name,
                    location = EXCLUDED.location,
                    variables = EXCLUDED.variables,
                    units = EXCLUDED.units,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    keywords = EXCLUDED.keywords,
                    raw_metadata = EXCLUDED.raw_metadata,
                    date_status = EXCLUDED.date_status,
                    synthetic = EXCLUDED.synthetic,
                    updated_at = NOW()
                """,
                body,
            )
            inserted.append(dataset_id)
    conn.commit()
    return inserted
