"""CLI for metadata validation, ingestion, search, and evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .db import connect, initialize, upsert
from .evaluate import evaluate
from .ingest import fetch_arm_metadata, normalize_arm_record, validate_jsonl
from .search import keyword_search

app = typer.Typer(help="Scientific metadata ingestion and retrieval")


@app.command()
def validate(path: Path):
    """Validate a JSONL file of dataset records."""
    result = validate_jsonl(path)
    typer.echo(json.dumps({"valid": len(result.records), "invalid": len(result.errors), "errors": result.errors}, indent=2))
    if result.errors:
        raise typer.Exit(code=1)


@app.command()
def ingest(path: Path | None = None, source: str = "synthetic", limit: int = 25):
    """Import metadata from the provided file or the public ARM metadata endpoint."""
    if source == "synthetic":
        if path is None:
            path = Path("fixtures/synthetic_arm_metadata.jsonl")
        result = validate_jsonl(path)
        if result.errors:
            typer.echo(json.dumps({"valid": len(result.records), "invalid": len(result.errors), "errors": result.errors}, indent=2))
            raise typer.Exit(code=1)
        records = result.records
    elif source == "arm":
        rows = fetch_arm_metadata(limit=limit)
        records = [normalize_arm_record(row) for row in rows]
    else:
        raise typer.BadParameter("source must be 'synthetic' or 'arm'")

    with connect() as conn:
        initialize(conn)
        count = upsert(conn, records)
    typer.echo(json.dumps({"source": source, "imported": count}, indent=2))


@app.command()
def search(query: str, limit: int = 10, source: str | None = None, site_code: str | None = None, site_name: str | None = None):
    """Search the PostgreSQL metadata index by keyword and supported filters."""
    with connect() as conn:
        results = keyword_search(conn, query, limit=limit, source=source, site_code=site_code, site_name=site_name)
    typer.echo(json.dumps(results, indent=2))


@app.command()
def evaluate_command(path: Path = Path("fixtures/retrieval_questions.json"), k: int = 5):
    """Evaluate retrieval using a deterministic query set."""
    with connect() as conn:
        report = evaluate(path, lambda query, limit: keyword_search(conn, query, limit=limit), k)
    typer.echo(json.dumps(report, indent=2))


if __name__ == "__main__":
    app()
