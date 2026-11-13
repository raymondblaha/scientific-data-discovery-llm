# Scientific Data Discovery

An evaluated, reproducible scientific metadata retrieval system, intended as a portfolio demonstration of research data systems engineering and later citation-grounded LLM applications.

**Milestone 1:** Pydantic JSONL validation, idempotent PostgreSQL ingestion, weighted keyword full-text search, and reproducible ranking evaluation. The included records are explicitly **synthetic demonstrations**, not actual catalog entries. No API key or hosted service is required.

## Run locally

```bash
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
sci-discover validate data/sample_datasets.jsonl
sci-discover ingest data/sample_datasets.jsonl
sci-discover search 'soil carbon'
sci-discover evaluate --k 5
pytest -q
```

See [Milestone 1 instructions](docs/milestone1.md) for data contracts, evaluation definitions, and next steps. Later milestones introduce semantic/hybrid retrieval, citation-grounded answers, and LLM evaluation.
