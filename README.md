# Scientific Data Discovery LLM Portfolio Project

This repository implements the first milestone of a reproducible scientific metadata discovery system. It focuses on public metadata acquisition, validation, PostgreSQL storage, keyword retrieval, and benchmark evaluation. It intentionally excludes LLM logic, embeddings, vector databases, and dashboards.

## Scope and architecture

- Acquisition: ARM public metadata via https://adc.arm.gov/elastic/metadata/_search and a synthetic fixture for offline evaluation.
- Canonical implementation: src/scientific_discovery/
- Compatibility layer: app/ re-exports the canonical modules without duplicating business logic.
- Validation: required field checks, URL validation, and malformed JSONL handling.
- Storage: PostgreSQL tables for normalized metadata and raw metadata retention.
- Retrieval: PostgreSQL full-text search with keyword and site filters.
- Evaluation: deterministic synthetic benchmark for Precision@5, Recall@5, Hit@5, and MRR@5.

## Verified implementation status

The following were verified in the current environment:

- Real ARM metadata ingestion succeeded for 25 records from the public ARM metadata endpoint.
- Repeated ingestion with the same source produced the same 25-row dataset count, confirming idempotence.
- PostgreSQL-backed keyword retrieval returned ranked ARM records for queries such as `temperature`, `cloud`, and `precipitation`.
- The canonical CLI executed successfully for validation, synthetic ingestion, and benchmark evaluation.
- The final repository state includes the canonical package under src/scientific_discovery and compatibility wrappers under app/ only.

## Setup

Requirements:

- Python 3.11+
- Docker Compose

Commands:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
docker compose up -d postgres
```

## Reproduction commands

Validate a JSONL file:

```bash
python -m scientific_discovery.cli validate fixtures/synthetic_arm_metadata.jsonl
```

Import the synthetic fixture:

```bash
python -m scientific_discovery.cli ingest --source synthetic
```

Import live ARM metadata (public metadata index, limit 25):

```bash
python -m scientific_discovery.cli ingest --source arm --limit 25
```

Keyword search:

```bash
python -m scientific_discovery.cli search "cloud fraction" --limit 10
```

Synthetic retrieval evaluation:

```bash
python -m scientific_discovery.cli evaluate-command --path fixtures/retrieval_questions.json --k 5
```

## Synthetic benchmark results

The benchmark output from the current project fixture is:

- Precision@5: 0.2
- Recall@5: 0.8
- Hit@5: 0.8
- MRR@5: 0.8

These are synthetic benchmark results only. They are not measured real-world retrieval accuracy for the ARM catalog or for domain-specific relevance judgments because the repository does not yet establish a curated real-world relevance set for ARM metadata.

## Test coverage and validation

Automated verification command:

```bash
pytest -q
```

Current result: 7 passing tests.

The suite covers:

- synthetic fixture validation
- malformed metadata rejection
- duplicate ingestion stability
- empty-search behavior
- date-overlap logic
- PostgreSQL integration/search behavior
- retrieval evaluation metrics

## Known limitations

- No real ARM relevance judgments have been established; the synthetic benchmark is intentionally small and not representative of production ranking quality.
- The ARM endpoint is a public metadata catalog, not a complete dataset-download service.
- The system does not yet include an LLM, embedding model, vector database, or dashboard.
- Database-backed workflows require a local PostgreSQL instance.

## Data retention and schema

Each imported record retains the source identifier, title, description, source URL, site metadata, date range, and raw JSON payload. Raw metadata is preserved to keep provenance and support later validation or debugging.

## Reproducibility notes

- The application depends on documented fixture files and public ARM metadata access.
- The database is started with Docker Compose using the local default PostgreSQL credentials in the example environment file.
- No restricted credentials or private ARM access tokens are committed to the repository.
