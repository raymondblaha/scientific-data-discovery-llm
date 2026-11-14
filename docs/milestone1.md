# Milestone 1: Ingestion and keyword retrieval baseline

## Scope

- JSONL ingestion with strict Pydantic validation and line-level error reports.
- Idempotent PostgreSQL upserts keyed by `dataset_id`.
- PostgreSQL full-text search with weighted title (A), description (B), and keywords (C).
- Versioned query relevance labels and macro retrieval metrics (Precision@k, Recall@k, Hit@k, MRR@k).
- Smoke test in CI, including PostgreSQL, and unit tests for validation/evaluation.

## Quickstart

```bash
cp .env.example .env
docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
sci-discover validate data/sample_datasets.jsonl
sci-discover ingest data/sample_datasets.jsonl
sci-discover search 'animal GPS movement'
sci-discover evaluate --k 5
pytest -q
```

The default database URL points to the Compose database. Set `DATABASE_URL` explicitly if using a different database. Search results are ranked by `ts_rank_cd` and ties break by `dataset_id`. Evaluation output is written to `reports/keyword_metrics.json`.

## Data contract

Each UTF-8 JSONL line is one dataset record. Required: `dataset_id`, `title`, `description`, `source`, `landing_page` (HTTP/HTTPS URL), and a non-empty `keywords` array. Optional: `publication_date` (ISO date), `license`. Unknown fields, invalid URLs, and duplicate IDs within one input file are rejected. The default ingestion mode is atomic with respect to validation: if any row fails validation, no rows are written. `--allow-invalid` opts into writing only valid rows. On repeat ingestion, records are updated by `dataset_id` rather than duplicated.

## Evaluation

The versioned `data/eval_queries.json` file contains query strings and manually curated `relevant_ids` sets. It is deliberately small and synthetic; results demonstrate pipeline mechanics, **not scientific retrieval quality**. Precision@k uses `k` as its denominator, Recall@k divides by total labeled relevant items, Hit@k indicates at least one match, and MRR@k uses the reciprocal rank of the first labeled relevant match. Search and retrieval evaluation do not call an LLM.

## Next improvements

Replace demo metadata with curated, licensed public catalog metadata (e.g. Data.gov, DOE OSTI, ESS-DIVE), retain original source IDs and provenance, add source-specific adapters, enlarge and independently adjudicate relevance labels, and report performance by dataset/source plus zero-result rates. Later milestones will add hybrid retrieval, citations, grounded generation, and faithfulness evaluation.
