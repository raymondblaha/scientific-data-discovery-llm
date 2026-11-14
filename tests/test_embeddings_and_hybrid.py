from scientific_discovery.embeddings import build_metadata_text, reciprocal_rank_fusion


def test_build_metadata_text_is_deterministic_and_includes_metadata_fields():
    record = {
        "source": "arm",
        "source_identifier": "arm-sgp-001",
        "title": "Aerosol Optical Depth",
        "description": "Measurements of aerosol optical depth at Southern Great Plains.",
        "site_name": "Southern Great Plains",
        "site_code": "sgp",
        "variables": [{"name": "aerosol optical depth"}, {"name": "cloud fraction"}],
        "raw_metadata": {"instrument_name": "MPL", "keywords": ["aerosol", "optical"]},
    }

    text = build_metadata_text(record)

    assert isinstance(text, str)
    assert "Aerosol Optical Depth" in text
    assert "Southern Great Plains" in text
    assert "aerosol optical depth" in text.lower()
    assert "MPL" in text
    assert text.count(" ") >= 5


def test_reciprocal_rank_fusion_combines_ranked_lists_deterministically():
    lexical = [
        {"dataset_id": "a", "score": 0.90},
        {"dataset_id": "b", "score": 0.70},
        {"dataset_id": "c", "score": 0.40},
    ]
    semantic = [
        {"dataset_id": "b", "score": 0.95},
        {"dataset_id": "d", "score": 0.80},
        {"dataset_id": "a", "score": 0.60},
    ]

    fused = reciprocal_rank_fusion(lexical, semantic, k=60)

    assert fused[0]["dataset_id"] == "b"
    assert fused[1]["dataset_id"] == "a"
    assert fused[2]["dataset_id"] == "d"
    assert all(row["score"] >= 0 for row in fused)
