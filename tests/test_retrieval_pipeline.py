import json
from pathlib import Path

import psycopg

from app.evaluation import evaluate_retrieval
from app.normalize import normalize_record
from app.search import filter_date_overlap, search_records
from app.storage import create_schema, import_records
from app.validate import validate_record
from scientific_discovery.db import connect as canonical_connect, initialize as canonical_initialize, upsert as canonical_upsert
from scientific_discovery.ingest import validate_jsonl
from scientific_discovery.search import keyword_search

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_arm_metadata.jsonl"
DB_URL = "postgresql://postgres:postgres@localhost:5432/arm_metadata"


def load_fixture_records():
    rows = []
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_synthetic_fixture_is_valid_and_normalized():
    rows = load_fixture_records()
    assert rows
    assert all(record.get("synthetic") is True for record in rows)
    assert all(validate_record(record)[0] for record in rows)
    normalized = normalize_record(rows[0])
    assert normalized["source_identifier"] == rows[0]["source_identifier"]
    assert normalized["raw_metadata"]["title"] == rows[0]["title"]


def test_date_overlap_distinguishes_unknown_coverage():
    record = {"start_date": "2020-01-01", "end_date": "2020-12-31"}
    assert filter_date_overlap(record, "2020-06-01", "2020-09-30")[0] == "overlap"
    assert filter_date_overlap({"start_date": None, "end_date": None}, "2020-06-01", "2020-09-30")[0] == "unknown"


def test_synthetic_fixture_validates_without_error():
    result = validate_jsonl(FIXTURE_PATH)
    assert result.errors == []
    assert len(result.records) == 5


def test_malformed_metadata_is_reported_as_error():
    bad_path = FIXTURE_PATH.with_name("bad_fixture.jsonl")
    bad_path.write_text('{"source": "synthetic", "title": "Missing source_identifier"}\n', encoding="utf-8")
    try:
        result = validate_jsonl(bad_path)
        assert result.errors
        assert any("source_identifier" in item["error"] for item in result.errors)
    finally:
        bad_path.unlink(missing_ok=True)


def test_duplicate_ingestion_keeps_count_stable():
    with canonical_connect() as conn:
        conn.execute("DROP TABLE IF EXISTS datasets")
        canonical_initialize(conn)
        rows = load_fixture_records()
        first = canonical_upsert(conn, [normalize_record(row) for row in rows])
        second = canonical_upsert(conn, [normalize_record(row) for row in rows])
        assert first == len(rows)
        assert second == len(rows)
        count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        assert count == len(rows)


def test_empty_keyword_search_returns_no_rows():
    with canonical_connect() as conn:
        canonical_initialize(conn)
        rows = keyword_search(conn, "definitely-not-present-anywhere", limit=5)
        assert rows == []


def test_database_import_search_and_evaluation_work():
    with psycopg.connect(DB_URL) as conn:
        create_schema(conn)
        rows = load_fixture_records()
        first = import_records(conn, rows)
        second = import_records(conn, rows)
        assert len(first) == len(rows)
        assert len(second) == len(rows)

        results = search_records(conn, keyword="aerosol", site_code="sgp", limit=10)
        assert len(results) >= 1
        assert all(item["site_code"] == "sgp" for item in results)
        assert any("aerosol" in (item["title"] or "").lower() for item in results)

        dated = search_records(conn, keyword="surface", start_date="2020-06-01", end_date="2020-09-30", limit=10)
        assert any(item["date_status"] == "overlap" for item in dated)

        summary = evaluate_retrieval(conn, Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_questions.json", limit=10)
        assert summary["questions"]
        assert summary["no_match_behavior"]["accuracy"] == 1.0
        assert summary["aggregates"]["development"]["avg_recall_at_k"] >= 0.0
