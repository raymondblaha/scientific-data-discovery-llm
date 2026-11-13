"""PostgreSQL smoke test; runs in CI, skips locally without a database."""
import psycopg
import pytest

from scientific_discovery.db import connect, initialize, upsert
from scientific_discovery.ingest import validate_jsonl
from scientific_discovery.search import keyword_search


def test_keyword_retrieval_and_idempotence():
    try:
        conn = connect()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL is not running")
    with conn:
        initialize(conn)
        from pathlib import Path
        records = validate_jsonl(Path("data/sample_datasets.jsonl")).records
        assert upsert(conn, records) == 5
        assert upsert(conn, records) == 5
        assert keyword_search(conn, "animal GPS movement")[0]["dataset_id"] == "demo:wildlife-003"
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM datasets WHERE dataset_id LIKE 'demo:%'")
            assert cur.fetchone()[0] == 5
