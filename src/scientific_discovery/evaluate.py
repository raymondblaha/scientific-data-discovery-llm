"""Information retrieval evaluation using fixed, labeled queries."""
import json
from pathlib import Path
from typing import Callable


def score_query(ranked_ids: list[str], relevant: set[str], k: int) -> dict:
    top = ranked_ids[:k]
    hits = sum(identifier in relevant for identifier in top)
    reciprocal_rank = next(
        (1.0 / rank for rank, item in enumerate(top, 1) if item in relevant), 0.0
    )
    return {
        f"precision_at_{k}": hits / k,
        f"recall_at_{k}": hits / len(relevant),
        f"hit_at_{k}": float(hits > 0),
        f"mrr_at_{k}": reciprocal_rank,
    }


def evaluate(path: Path, search: Callable[[str, int], list[dict]], k: int = 5) -> dict:
    if k < 1:
        raise ValueError("k must be >= 1")
    samples = json.loads(path.read_text(encoding="utf-8"))
    if not samples:
        raise ValueError("evaluation set cannot be empty")
    per_query = []
    for item in samples:
        relevant = set(item["relevant_ids"])
        if not relevant:
            raise ValueError(f"query {item['query']!r} has no relevant_ids")
        ranked = [row["dataset_id"] for row in search(item["query"], k)]
        per_query.append({"query": item["query"], "relevant_ids": sorted(relevant),
                          "retrieved_ids": ranked, **score_query(ranked, relevant, k)})
    metrics = {name: sum(row[name] for row in per_query) / len(per_query)
               for name in (f"precision_at_{k}", f"recall_at_{k}",
                            f"hit_at_{k}", f"mrr_at_{k}")}
    return {"queries": len(per_query), "k": k, "metrics": metrics, "per_query": per_query}
