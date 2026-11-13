"""PostgreSQL schema and idempotent dataset upserts."""
import os

import psycopg
from psycopg.types.json import Jsonb

from .models import Dataset


def connect():
    return psycopg.connect(os.environ.get(
        "DATABASE_URL", "postgresql://scientific:scientific@localhost:5432/scientific"
    ))


def initialize(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                landing_page TEXT NOT NULL,
                keywords JSONB NOT NULL,
                publication_date DATE,
                license TEXT,
                search_vector TSVECTOR NOT NULL
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS datasets_search_idx ON datasets USING GIN(search_vector)"
        )
    conn.commit()


def upsert(conn, records: list[Dataset]) -> int:
    with conn.cursor() as cur:
        for record in records:
            cur.execute("""
                INSERT INTO datasets (
                    dataset_id, title, description, source, landing_page, keywords,
                    publication_date, license, search_vector
                ) VALUES (
                    %(dataset_id)s, %(title)s, %(description)s, %(source)s,
                    %(landing_page)s, %(keywords)s, %(publication_date)s, %(license)s,
                    setweight(to_tsvector('english', %(title)s), 'A') ||
                    setweight(to_tsvector('english', %(description)s), 'B') ||
                    setweight(to_tsvector('english', %(keyword_text)s), 'C')
                ) ON CONFLICT (dataset_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    source = EXCLUDED.source,
                    landing_page = EXCLUDED.landing_page,
                    keywords = EXCLUDED.keywords,
                    publication_date = EXCLUDED.publication_date,
                    license = EXCLUDED.license,
                    search_vector = EXCLUDED.search_vector
            """, {
                **record.model_dump(exclude={"landing_page", "keywords"}),
                "landing_page": str(record.landing_page),
                "keywords": Jsonb(record.keywords),
                "keyword_text": " ".join(record.keywords),
            })
    conn.commit()
    return len(records)
