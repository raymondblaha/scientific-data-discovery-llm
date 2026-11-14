#!/usr/bin/env python3
"""Generate a real-ARM benchmark for lexical, semantic, and hybrid retrieval."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any

from scientific_discovery.db import connect, initialize, upsert, upsert_embeddings
from scientific_discovery.ingest import fetch_arm_metadata, normalize_arm_record
from scientific_discovery.search import hybrid_search, keyword_search, semantic_search

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
BENCHMARK_PATH = RESULTS_DIR / "arm_benchmark_results.json"
CSV_PATH = RESULTS_DIR / "arm_benchmark_results.csv"
PLOT_PATH = RESULTS_DIR / "arm_retrieval_comparison.png"
SOURCE_URL = "https://adc.arm.gov/elastic/metadata/_search"
SOURCE_NOTE = "Public ARM metadata catalog query: q=*:* and size=N; retrieved without authentication."

QUERY_SET = [
    {
        "query": "ozone",
        "expected_ids": [
            "10330_tbsozonesonde_lwbroad_tbsozonesonde_atmprof_ozoneconc",
            "10330_tbsozonesonde_lwnarrow_tbsozonesonde_atmprof_ozoneconc",
            "10330_tbsozonesonde_macro_tbsozonesonde_atmprof_ozoneconc",
            "10330_tbsozonesonde_lwbroad_tbsozonesonde_airborne_ozoneconc",
            "10330_tbsozonesonde_lwnarrow_tbsozonesonde_airborne_ozoneconc",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "temperature",
        "expected_ids": [
            "16_lwbroad_capt2int_derivmod_skintemp",
            "16_lwnarrow_capt2int_derivmod_skintemp",
            "16_macro_capt2int_derivmod_skintemp",
            "16_sfcmet_capt2int_derivmod_skintemp",
            "16_sfcflux_capt2int_derivmod_skintemp",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "wind",
        "expected_ids": [
            "10330_tbsozoneground_lwbroad_tbsozoneground_airborne_horizwind",
            "10330_tbsozoneground_lwbroad_tbsozoneground_other_horizwind",
            "10330_tbsozoneground_lwnarrow_tbsozoneground_airborne_horizwind",
            "10330_tbsozoneground_macro_tbsozoneground_other_horizwind",
            "10330_tbsozoneground_macro_tbsozoneground_airborne_horizwind",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "cloud",
        "expected_ids": [
            "20_lwbroad_tropcldpropradheat_derivmod_liquidwc",
            "20_sfcmet_tropcldpropradheat_derivmod_liquidwc",
            "20_sfcstate_tropcldpropradheat_derivmod_liquidwc",
            "20_micro_tropcldpropradheat_derivmod_liquidwc",
            "20_upperair_tropcldpropradheat_derivmod_liquidwc",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "precipitation",
        "expected_ids": [
            "10330_tbsozoneground_lwbroad_tbsozoneground_airborne_atmmoist",
            "10330_tbsozoneground_lwbroad_tbsozoneground_other_atmmoist",
            "10330_tbsozoneground_lwnarrow_tbsozoneground_airborne_atmmoist",
            "10330_tbsozoneground_lwnarrow_tbsozoneground_other_atmmoist",
            "10330_tbsozoneground_macro_tbsozoneground_airborne_atmmoist",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "aerosol",
        "expected_ids": [
            "437_upperair_caps-ssa-comp_aerosol_aerosextinct",
            "437_micro_caps-ssa-comp_aerosol_aerosextinct",
            "437_macro_caps-ssa-comp_aerosol_aerosextinct",
            "437_lwbroad_caps-ssa-comp_aerosol_aerosextinct",
            "437_lwnarrow_caps-ssa-comp_aerosol_aerosextinct",
        ],
        "judgment_status": "provisional",
        "split": "development",
    },
    {
        "query": "quantum gravity atmospheric chemistry",
        "expected_ids": [],
        "judgment_status": "provisional",
        "split": "held_out",
    },
]


def make_id_list(results: list[dict[str, Any]]) -> list[str]:
    return [row.get("source_identifier") or row.get("dataset_id") for row in results]


def dcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    total = 0.0
    for rank, dataset_id in enumerate(retrieved_ids[:k], start=1):
        if dataset_id in relevant_ids:
            total += (2**1 - 1) / math.log2(rank + 1)
    return total


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    ideal_relevant = list(relevant_ids)[:k]
    ideal_score = dcg_at_k(ideal_relevant, relevant_ids, k)
    if ideal_score <= 0:
        return 0.0
    return dcg_at_k(retrieved_ids, relevant_ids, k) / ideal_score


def score_question(retrieved_ids: list[str], expected_ids: list[str], k: int = 5) -> dict[str, float]:
    relevant = set(expected_ids)
    if not expected_ids:
        hit = 1.0 if not retrieved_ids else 0.0
        return {
            f"precision_at_{k}": 0.0,
            f"recall_at_{k}": 0.0,
            f"hit_at_{k}": hit,
            f"mrr_at_{k}": 0.0,
            "ndcg_at_10": 0.0,
        }

    top = retrieved_ids[:k]
    hits = sum(item in relevant for item in top)
    precision = hits / max(1, k)
    recall = hits / len(relevant)
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
        "ndcg_at_10": ndcg_at_k(retrieved_ids, relevant, 10),
    }


def evaluate_method(conn: Any, method_name: str, questions: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    per_question: list[dict[str, Any]] = []
    latencies: list[float] = []

    method_map = {
        "lexical": keyword_search,
        "semantic": semantic_search,
        "hybrid": hybrid_search,
    }
    search_fn = method_map[method_name]

    for item in questions:
        start = time.perf_counter()
        results = search_fn(conn, item["query"], limit=10)
        latency_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(latency_ms)

        retrieved_ids = make_id_list(results)
        evaluated = score_question(retrieved_ids, item.get("expected_ids", []), k)
        per_question.append(
            {
                "query": item["query"],
                "expected_ids": item.get("expected_ids", []),
                "retrieved_ids": retrieved_ids,
                "judgment_status": item.get("judgment_status", "provisional"),
                "split": item.get("split", "development"),
                "latency_ms": round(latency_ms, 3),
                **evaluated,
            }
        )

    aggregate_keys = [
        "precision_at_5",
        "recall_at_5",
        "hit_at_5",
        "mrr_at_5",
        "ndcg_at_10",
    ]
    metrics = {
        key: round(sum(row[key] for row in per_question) / max(1, len(per_question)), 6)
        for key in aggregate_keys
    }
    no_match_questions = [row for row in per_question if not row["expected_ids"]]
    no_match_accuracy = 0.0
    if no_match_questions:
        no_match_accuracy = sum(1.0 for row in no_match_questions if not row["retrieved_ids"]) / len(no_match_questions)
    return {
        "method": method_name,
        "queries": len(per_question),
        "metrics": metrics,
        "latency_ms": {
            "median": round(statistics.median(latencies), 3),
            "p95": round(statistics.quantiles(latencies, n=100)[94], 3) if len(latencies) >= 2 else round(latencies[0], 3) if latencies else 0.0,
        },
        "no_match_behavior": {
            "accuracy": round(no_match_accuracy, 6),
            "count": len(no_match_questions),
        },
        "per_question": per_question,
    }


def write_csv(summary_rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "method",
        "precision_at_5",
        "recall_at_5",
        "hit_at_5",
        "mrr_at_5",
        "ndcg_at_10",
        "median_latency_ms",
        "p95_latency_ms",
        "no_match_accuracy",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(
                {
                    "method": row["method"],
                    "precision_at_5": row["metrics"]["precision_at_5"],
                    "recall_at_5": row["metrics"]["recall_at_5"],
                    "hit_at_5": row["metrics"]["hit_at_5"],
                    "mrr_at_5": row["metrics"]["mrr_at_5"],
                    "ndcg_at_10": row["metrics"]["ndcg_at_10"],
                    "median_latency_ms": row["latency_ms"]["median"],
                    "p95_latency_ms": row["latency_ms"]["p95"],
                    "no_match_accuracy": row["no_match_behavior"]["accuracy"],
                }
            )


def render_plot(summary_rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to generate the benchmark visualization") from exc

    labels = [row["method"] for row in summary_rows]
    metrics = [
        "precision_at_5",
        "recall_at_5",
        "mrr_at_5",
        "ndcg_at_10",
    ]
    positions = list(range(len(labels)))
    width = 0.18
    fig, ax = plt.subplots(figsize=(10, 6))
    for index, metric_name in enumerate(metrics):
        values = [row["metrics"][metric_name] * 100.0 for row in summary_rows]
        ax.bar([pos + (index - 1.5) * width for pos in positions], values, width=width, label=metric_name.replace("_", " ").upper())
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Score (%)")
    ax.set_title("ARM retrieval methods: lexical vs semantic vs hybrid")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=200)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    conn = connect()
    initialize(conn)
    rows = fetch_arm_metadata(limit=500)
    records = [normalize_arm_record(row) for row in rows]
    upsert(conn, records)
    upsert_embeddings(conn, records)

    summary_rows: list[dict[str, Any]] = []
    for method in ("lexical", "semantic", "hybrid"):
        summary_rows.append(evaluate_method(conn, method, QUERY_SET, k=5))

    payload = {
        "corpus": {
            "source": "ARM metadata endpoint",
            "source_url": SOURCE_URL,
            "retrieved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ingested_records": len(records),
            "unique_source_identifiers": len({record.source_identifier for record in records}),
            "synthetic_records": 0,
            "judgment_status": "provisional",
            "deduplicated": True,
            "notes": "Public ARM metadata catalog query q=*:* and size=N. Records were normalized and deduplicated by source_identifier before benchmarking.",
        },
        "model": {
            "name": os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
            "device": os.environ.get("EMBEDDING_DEVICE", "cpu").strip().lower() or "cpu",
            "dimension": 384,
            "source": "sentence-transformers",
        },
        "relevance_judgments": {
            "status": "provisional",
            "coverage": "Manual selection from the same ARM corpus; not exhaustive and may bias comparisons toward tokens that were explicitly included in the judgment set.",
            "method": "Selected by inspection from the live corpus; relevance labels are not adjudicated by an external benchmark committee.",
        },
        "queries": QUERY_SET,
        "results_by_method": summary_rows,
    }
    BENCHMARK_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv(summary_rows)
    render_plot(summary_rows)

    print(json.dumps({
        "records_ingested": len(records),
        "benchmark_json": str(BENCHMARK_PATH),
        "benchmarks_csv": str(CSV_PATH),
        "chart_png": str(PLOT_PATH),
        "method_summary": {row["method"]: row["metrics"] for row in summary_rows},
    }, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
