"""PostgreSQL schema and idempotent dataset upserts."""

from __future__ import annotations

import os
from collections.abc import Iterable

import psycopg
from psycopg.types.json import Jsonb

from .models import Dataset, SourceDataset


def connect() -> psycopg.Connection:
    return psycopg.connect(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/arm_metadata",
        )
    )


def initialize(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                landing_page TEXT NOT NULL,
                keywords JSONB NOT NULL,
                publication_date DATE,
                license TEXT,
                search_vector TSVECTOR NOT NULL,
                source_identifier TEXT,
                source_url TEXT,
                location TEXT,
                site_code TEXT,
                site_name TEXT,
                start_date DATE,
                end_date DATE,
                acquisition_timestamp TIMESTAMPTZ,
                source_content_hash TEXT,
                raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                synthetic BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS datasets_search_idx ON datasets USING GIN(search_vector)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS datasets_source_idx ON datasets (source, source_identifier)"
        )
    conn.commit()


def upsert(conn: psycopg.Connection, records: Iterable[Dataset | SourceDataset | dict[str, object]]) -> int:
    count = 0
    with conn.cursor() as cur:
        for record in records:
            if isinstance(record, dict):
                normalized = record.get("source_identifier") is not None
                looks_like_dataset = bool(record.get("landing_page")) and isinstance(record.get("keywords"), list) and len(record.get("keywords") or []) > 0
                if normalized and not looks_like_dataset:
                    record = SourceDataset.model_validate(record)
                else:
                    record = Dataset.model_validate(record)

            if isinstance(record, Dataset):
                dataset_id = record.dataset_id
                title = record.title
                description = record.description
                source = record.source
                landing_page = record.landing_page
                keywords = record.keywords
                publication_date = record.publication_date
                license = record.license
                source_identifier = None
                source_url = None
                location = None
                site_code = None
                site_name = None
                start_date = None
                end_date = None
                acquisition_timestamp = None
                source_content_hash = None
                raw_metadata = {}
                synthetic = False
            else:
                dataset_id = str(record.source_identifier)
                title = record.title or record.source_identifier
                description = record.description or ""
                source = record.source
                landing_page = record.source_url or ""
                keywords = []
                if record.title:
                    keywords.extend(record.title.split())
                if record.description:
                    keywords.extend(record.description.split())
                if record.site_name:
                    keywords.append(record.site_name)
                if record.site_code:
                    keywords.append(record.site_code)
                if record.variables:
                    for variable in record.variables:
                        if isinstance(variable, dict) and isinstance(variable.get("name"), str):
                            keywords.append(variable["name"])
                keywords = list(dict.fromkeys(keyword.strip().lower() for keyword in keywords if keyword and keyword.strip()))
                publication_date = record.start_date
                license = None
                source_identifier = record.source_identifier
                source_url = record.source_url
                location = record.location
                site_code = record.site_code
                site_name = record.site_name
                start_date = record.start_date
                end_date = record.end_date
                acquisition_timestamp = record.acquisition_timestamp
                source_content_hash = record.source_content_hash
                raw_metadata = record.raw_metadata or {}
                synthetic = bool(record.synthetic)

            cur.execute(
                """
                INSERT INTO datasets (
                    dataset_id, title, description, source, landing_page,
                    keywords, publication_date, license, search_vector,
                    source_identifier, source_url, location, site_code, site_name,
                    start_date, end_date, acquisition_timestamp, source_content_hash,
                    raw_metadata, synthetic, updated_at
                ) VALUES (
                    %(dataset_id)s, %(title)s, %(description)s, %(source)s,
                    %(landing_page)s, %(keywords)s, %(publication_date)s,
                    %(license)s,
                    setweight(to_tsvector('english', %(title)s), 'A') ||
                    setweight(to_tsvector('english', %(description)s), 'B') ||
                    setweight(to_tsvector('english', %(keyword_text)s), 'C'),
                    %(source_identifier)s, %(source_url)s, %(location)s,
                    %(site_code)s, %(site_name)s, %(start_date)s, %(end_date)s,
                    %(acquisition_timestamp)s, %(source_content_hash)s,
                    %(raw_metadata)s, %(synthetic)s, NOW()
                ) ON CONFLICT (dataset_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    source = EXCLUDED.source,
                    landing_page = EXCLUDED.landing_page,
                    keywords = EXCLUDED.keywords,
                    publication_date = EXCLUDED.publication_date,
                    license = EXCLUDED.license,
                    search_vector = EXCLUDED.search_vector,
                    source_identifier = EXCLUDED.source_identifier,
                    source_url = EXCLUDED.source_url,
                    location = EXCLUDED.location,
                    site_code = EXCLUDED.site_code,
                    site_name = EXCLUDED.site_name,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    acquisition_timestamp = EXCLUDED.acquisition_timestamp,
                    source_content_hash = EXCLUDED.source_content_hash,
                    raw_metadata = EXCLUDED.raw_metadata,
                    synthetic = EXCLUDED.synthetic,
                    updated_at = NOW()
                """,
                {
                    "dataset_id": dataset_id,
                    "title": title,
                    "description": description,
                    "source": source,
                    "landing_page": landing_page,
                    "keywords": Jsonb(keywords),
                    "publication_date": publication_date,
                    "license": license,
                    "keyword_text": " ".join(keywords),
                    "source_identifier": source_identifier,
                    "source_url": source_url,
                    "location": location,
                    "site_code": site_code,
                    "site_name": site_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "acquisition_timestamp": acquisition_timestamp,
                    "source_content_hash": source_content_hash,
                    "raw_metadata": Jsonb(raw_metadata),
                    "synthetic": synthetic,
                },
            )
            count += 1
    conn.commit()
    return count
