"""PostgreSQL schema and idempotent dataset upserts."""

from __future__ import annotations

import os
from collections.abc import Iterable

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from .config import get_embedding_dimension, get_embedding_model_name
from .embeddings import build_metadata_text, generate_embeddings
from .models import Dataset, SourceDataset


def connect() -> psycopg.Connection:
    conn = psycopg.connect(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/arm_metadata",
        )
    )
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
        register_vector(conn)
    except (AttributeError, TypeError, ValueError, psycopg.ProgrammingError):
        pass
    return conn


def initialize(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
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
            "CREATE TABLE IF NOT EXISTS dataset_embeddings (\n"
            "    dataset_id TEXT PRIMARY KEY REFERENCES datasets(dataset_id) ON DELETE CASCADE,\n"
            "    model_name TEXT NOT NULL,\n"
            "    model_version TEXT NOT NULL,\n"
            "    embedding_dimension INTEGER NOT NULL,\n"
            "    text_hash TEXT NOT NULL,\n"
            "    embedding VECTOR(384) NOT NULL,\n"
            "    embedding_text TEXT NOT NULL,\n"
            "    source TEXT NOT NULL DEFAULT 'arm',\n"
            "    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n"
            "    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()\n"
            ")"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS datasets_search_idx ON datasets USING GIN(search_vector)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS datasets_source_idx ON datasets (source, source_identifier)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS dataset_embeddings_vector_idx ON dataset_embeddings USING hnsw (embedding vector_cosine_ops)"
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


def upsert_embeddings(conn: psycopg.Connection, records: Iterable[Dataset | SourceDataset | dict[str, object]], model_name: str | None = None, model_version: str | None = None) -> int:
    rows = list(records)
    if not rows:
        return 0

    model_name = model_name or get_embedding_model_name()
    model_version = model_version or "sentence-transformers"
    dimension = get_embedding_dimension()

    row_entries: list[tuple[str, dict[str, object], str]] = []
    for record in rows:
        source_record = record if isinstance(record, dict) else record.model_dump()
        dataset_id = source_record.get("dataset_id") or source_record.get("source_identifier")
        if dataset_id is None:
            continue
        text = build_metadata_text(source_record)
        row_entries.append((str(dataset_id), source_record, text))

    if not row_entries:
        return 0

    dataset_ids = [dataset_id for dataset_id, _, _ in row_entries]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, text_hash, model_name FROM dataset_embeddings WHERE dataset_id = ANY(%s)",
            (dataset_ids,),
        )
        existing_rows = {row[0]: {"text_hash": row[1], "model_name": row[2]} for row in cur.fetchall()}

    pending: list[tuple[str, dict[str, object], str]] = []
    for dataset_id, source_record, text in row_entries:
        text_hash = __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()
        existing = existing_rows.get(dataset_id)
        if existing and existing["text_hash"] == text_hash and existing["model_name"] == model_name:
            continue
        pending.append((dataset_id, source_record, text))

    if not pending:
        return 0

    texts = [text for _, _, text in pending]
    embeddings = generate_embeddings(texts, model_name=model_name)

    count = 0
    with conn.cursor() as cur:
        for (dataset_id, source_record, text), vector in zip(pending, embeddings):
            text_hash = __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()
            cur.execute(
                """
                INSERT INTO dataset_embeddings (
                    dataset_id, model_name, model_version, embedding_dimension,
                    text_hash, embedding, embedding_text, source
                ) VALUES (
                    %(dataset_id)s, %(model_name)s, %(model_version)s, %(embedding_dimension)s,
                    %(text_hash)s, %(embedding)s, %(embedding_text)s, %(source)s
                ) ON CONFLICT (dataset_id) DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    model_version = EXCLUDED.model_version,
                    embedding_dimension = EXCLUDED.embedding_dimension,
                    text_hash = EXCLUDED.text_hash,
                    embedding = EXCLUDED.embedding,
                    embedding_text = EXCLUDED.embedding_text,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                """,
                {
                    "dataset_id": str(dataset_id),
                    "model_name": model_name,
                    "model_version": model_version,
                    "embedding_dimension": dimension,
                    "text_hash": text_hash,
                    "embedding": vector,
                    "embedding_text": text,
                    "source": source_record.get("source") or "arm",
                },
            )
            count += 1
    conn.commit()
    return count
