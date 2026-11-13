import json

from scientific_discovery.ingest import validate_jsonl


def test_fixture_is_valid():
    from pathlib import Path
    result = validate_jsonl(Path("data/sample_datasets.jsonl"))
    assert len(result.records) == 5
    assert not result.errors


def test_invalid_and_duplicate_report_line_numbers(tmp_path):
    good = {"dataset_id": "id:1", "title": "Title", "description": "Description",
            "source": "source", "landing_page": "https://example.org/1", "keywords": ["tag"]}
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join([json.dumps(good), json.dumps(good), "not json"]))
    result = validate_jsonl(path)
    assert len(result.records) == 1
    assert [error["line"] for error in result.errors] == [2, 3]
