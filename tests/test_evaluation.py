from pathlib import Path

from scientific_discovery.evaluate import evaluate, score_query


def test_metrics_for_one_relevant_item():
    scores = score_query(["irrelevant", "relevant"], {"relevant"}, 5)
    assert scores == {"precision_at_5": 0.2, "recall_at_5": 1.0,
                      "hit_at_5": 1.0, "mrr_at_5": 0.5}


def test_evaluation_fixture_with_mock_retriever():
    mapping = {"air temperature": "demo:climate-001", "river streamflow": "demo:water-002",
               "animal GPS movement": "demo:wildlife-003", "soil carbon": "demo:soil-004",
               "solar radiation": "demo:solar-005"}
    report = evaluate(Path("data/eval_queries.json"),
                      lambda query, limit: [{"dataset_id": mapping[query]}], 5)
    assert report["metrics"]["recall_at_5"] == 1.0
    assert report["metrics"]["mrr_at_5"] == 1.0
