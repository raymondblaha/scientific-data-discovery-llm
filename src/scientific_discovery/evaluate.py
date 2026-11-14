"""Retrieval metrics for scientific metadata queries."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .search import search_records


def score_query(retrieved_ids: list[str], expected_ids: list[str], k: int) -> dict[str, float]:
    relevant = set(expected_ids)
    top = retrieved_ids[:k]
    hits = sum(item in relevant for item in top)
    precision = hits / max(1, k)
    recall = hits / len(relevant) if relevant else 0.0
    hit = 1.0 if hits > 0 else 0.0
    reciprocal_rank = 0.0
    for index, item in enumerate(top, start=1):
        if item in relevant:
            reciprocal_rank = 1.0 / index
            break
    return {
        f"precision_at_{k}": precision,
        f"recall_at_{k}": recall,
        f"hit_at_{k}": hit,
        f"mrr_at_{k}": reciprocal_rank,
    }


def evaluate(path: Path | str, search: Callable[[str, int], list[dict[str, Any]]], k: int = 5) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be >= 1")
    samples = json.loads(Path(path).read_text(encoding="utf-8"))
    if not samples:
        raise ValueError("evaluation set cannot be empty")

    per_query: list[dict[str, Any]] = []
    for item in samples:
        relevant = set(item.get("expected_ids") or item.get("relevant_ids") or [])
        ranked = [row["dataset_id"] for row in search(item["query"], k)]
        per_query.append(
            {
                "query": item["query"],
                "relevant_ids": sorted(relevant),
                "retrieved_ids": ranked,
                **score_query(ranked, sorted(relevant), k),
            }
        )

    metrics = {
        name: sum(row[name] for row in per_query) / len(per_query)
        for name in (f"precision_at_{k}", f"recall_at_{k}", f"hit_at_{k}", f"mrr_at_{k}")
    }
    return {
        "queries": len(per_query),
        "k": k,
        "metrics": metrics,
        "per_query": per_query,
    }


def evaluate_retrieval(conn, questions_path: str | Path, limit: int = 10) -> dict[str, Any]:
    path = Path(questions_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    per_question: list[dict[str, Any]] = []
    grouped: dict[str, list[float]] = {"development": [], "held_out": []}
    no_match_hits = 0
    no_match_questions = 0

    for item in records:
        results = search_records(
            conn,
            keyword=item["query"],
            site_code=item.get("site_code"),
            site_name=item.get("site_name"),
            source=item.get("source"),
            limit=limit,
        )
        retrieved_ids = [row.get("source_identifier") or row.get("dataset_id") for row in results]
        expected_ids = item.get("expected_ids", [])
        scores = score_query(retrieved_ids, expected_ids, limit)
        per_question.append({
            "query": item["query"],
            "expected_ids": expected_ids,
            "retrieved_ids": retrieved_ids,
            **scores,
        })

        split = item.get("split", "development")
        if split in grouped:
            grouped[split].append(scores[f"recall_at_{limit}"])

        if not expected_ids:
            no_match_questions += 1
            no_match_hits += 1 if not retrieved_ids else 0

    aggregates: dict[str, dict[str, float | int]] = {}
    for split_name, values in grouped.items():
        aggregates[split_name] = {
            "count": len(values),
            "avg_recall_at_k": (sum(values) / len(values)) if values else 0.0,
        }

    no_match_accuracy = (no_match_hits / no_match_questions) if no_match_questions else 1.0

    return {
        "questions": len(per_question),
        "limit": limit,
        "aggregates": aggregates,
        "no_match_behavior": {
            "accuracy": no_match_accuracy,
            "count": no_match_questions,
        },
        "per_question": per_question,
    }
