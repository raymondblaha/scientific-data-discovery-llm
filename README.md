# Scientific Data Discovery LLM Portfolio Project

This repository implements a reproducible scientific metadata discovery system focused on public metadata acquisition, validation, PostgreSQL storage, keyword search, semantic retrieval, hybrid retrieval, and benchmark evaluation. It intentionally excludes LLM logic, chat interfaces, vector databases beyond pgvector, and dashboards.

## Scope and architecture

- Acquisition: ARM public metadata via https://adc.arm.gov/elastic/metadata/_search and synthetic fixtures for offline evaluation.
- Canonical implementation: src/scientific_discovery/
- Compatibility layer: app/ re-exports the canonical modules without duplicating business logic.
- Validation: required field checks, URL validation, malformed JSONL handling, and duplicate detection.
- Storage: PostgreSQL with pgvector support for normalized metadata, raw metadata retention, and embedding storage.
- Retrieval: PostgreSQL full-text search, semantic similarity search, and reciprocal-rank fusion hybrid retrieval.
- Evaluation: deterministic synthetic benchmarks plus a live ARM benchmark exported to JSON, CSV, and a chart.

## Verified implementation status

The following were verified in the current environment:

- PostgreSQL + pgvector initialized successfully with Docker Compose, and the database-backed pipeline executed on a live ARM corpus.
- Real ARM metadata ingestion succeeded for 500 records from the public metadata endpoint.
- Embedding generation using `sentence-transformers/all-MiniLM-L6-v2` produced valid 384-dimensional vectors and stored them in the `dataset_embeddings` table.
- Rerunning embedding generation for unchanged records was verified to skip updates and leave the row count stable.
- Lexical, semantic, and hybrid searches all executed successfully against the real PostgreSQL database.
- The canonical CLI and benchmark script executed successfully for live ARM verification and export.
- The project remains scoped to the scientific metadata system; the Colibri workspace and model cache remain excluded from tracking.

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

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Validate a JSONL file:

```bash
python -m scientific_discovery.cli validate fixtures/synthetic_arm_metadata.jsonl
```

Import the synthetic fixture:

```bash
python -m scientific_discovery.cli ingest --source synthetic
```

Import live ARM metadata (public metadata index, limit 500):

```bash
python - <<'PY'
from scientific_discovery.db import connect, initialize, upsert
from scientific_discovery.ingest import fetch_arm_metadata, normalize_arm_record

conn = connect()
initialize(conn)
rows = fetch_arm_metadata(limit=500)
records = [normalize_arm_record(row) for row in rows]
print(upsert(conn, records))
conn.close()
PY
```

Generate and store sentence-transformer embeddings for a loaded corpus:

```bash
python - <<'PY'
from scientific_discovery.db import connect, upsert_embeddings
from scientific_discovery.ingest import fetch_arm_metadata, normalize_arm_record

conn = connect()
rows = fetch_arm_metadata(limit=500)
records = [normalize_arm_record(row) for row in rows]
print(upsert_embeddings(conn, records))
conn.close()
PY
```

Keyword search:

```bash
python -m scientific_discovery.cli search "cloud" --mode lexical --limit 10
```

Semantic search:

```bash
python -m scientific_discovery.cli search "cloud" --mode semantic --limit 10
```

Hybrid search:

```bash
python -m scientific_discovery.cli search "cloud" --mode hybrid --limit 10
```

Synthetic retrieval evaluation:

```bash
python -m scientific_discovery.cli evaluate-command --path fixtures/retrieval_questions.json --k 5
```

Real ARM retrieval benchmark with export to JSON, CSV, and a comparison chart:

```bash
python scripts/real_arm_benchmark.py
```

## Real ARM benchmark results

The live benchmark was generated from 500 ARM metadata records and compared lexical, semantic, and hybrid retrieval using provisional relevance judgments selected from the same corpus.

- Hybrid retrieval: Precision@5 = 0.542857, Recall@5 = 0.542857, Hit@5 = 0.857143, MRR@5 = 0.742857, nDCG@10 = 0.702175, median latency = 1861.548 ms, p95 latency = 2178.851 ms
- Lexical retrieval: Precision@5 = 0.485714, Recall@5 = 0.485714, Hit@5 = 0.857143, MRR@5 = 0.6, nDCG@10 = 0.65984, median latency = 1.488 ms, p95 latency = 4.779 ms
- Semantic retrieval: Precision@5 = 0.285714, Recall@5 = 0.285714, Hit@5 = 0.428571, MRR@5 = 0.357143, nDCG@10 = 0.328891, median latency = 1873.871 ms, p95 latency = 1964.624 ms

These results are provisional because the relevance labels were curated manually from the live corpus rather than through a full adjudicated benchmark process. The benchmark artifacts are stored in `results/arm_benchmark_results.json`, `results/arm_benchmark_results.csv`, and `results/arm_retrieval_comparison.png`.

The benchmark intentionally covers a 500-record ARM sample and does not claim broad scientific generalization. The query set includes one held-out no-match query, and the manual judgments are stored as provisional rather than canonical ground truth.

## Test coverage and validation

Automated verification command:

```bash
pytest -q
```

Current project result: 16 passing tests, including the PostgreSQL integration test file executed against the live local database.

The suite covers:

- synthetic fixture validation
- malformed metadata rejection
- duplicate ingestion stability
- empty-search behavior
- date-overlap logic
- PostgreSQL integration/search behavior
- retrieval evaluation metrics
- embedding idempotence and hybrid retrieval regression checks

## Known limitations

- The ARM endpoint is a public metadata catalog and does not provide a curated adjudicated relevance set; the benchmark judgments are provisional.
- The 500-record benchmark is a sample used for reproducible retrieval validation, not a production-scale scientific benchmark.
- The semantic retrieval path depends on the local `sentence-transformers` model and a CPU-friendly configuration.
- The project does not yet include an LLM, vector database aside from pgvector, or a dashboard.
- Database-backed workflows require a local PostgreSQL instance started with Docker Compose.

## Data retention and schema

Each imported record retains the source identifier, title, description, source URL, site metadata, date range, and raw JSON payload. Raw metadata is preserved to keep provenance and support later validation or debugging.

## Reproducibility notes

- The application depends on documented fixture files and public ARM metadata access.
- The local database is started with Docker Compose using the default PostgreSQL credentials in the example environment file.
- No restricted credentials, model weights, or caches are tracked in the repository; the external Colibri workspace and model cache remain outside the project path and are ignored by Git.
