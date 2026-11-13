"""Small command-line interface for milestone-one workflows."""
import json
from pathlib import Path

import typer

from .db import connect, initialize, upsert
from .evaluate import evaluate
from .ingest import validate_jsonl
from .search import keyword_search

app = typer.Typer(help="Scientific metadata ingestion and retrieval")


@app.command()
def ingest(path: Path, strict: bool = typer.Option(True, "--strict/--allow-invalid")):
    """Validate JSONL and upsert into PostgreSQL."""
    result = validate_jsonl(path)
    typer.echo(json.dumps({"valid": len(result.records), "invalid": len(result.errors),
                           "errors": result.errors}, indent=2))
    if strict and result.errors:
        raise typer.Exit(code=1)
    with connect() as conn:
        initialize(conn)
        count = upsert(conn, result.records)
    typer.echo(f"Upserted {count} datasets")


@app.command()
def validate(path: Path):
    """Validate a JSONL file without database access."""
    result = validate_jsonl(path)
    typer.echo(json.dumps({"valid": len(result.records), "invalid": len(result.errors),
                           "errors": result.errors}, indent=2))
    if result.errors:
        raise typer.Exit(code=1)


@app.command()
def search(query: str, limit: int = 10):
    """Search datasets by keywords."""
    with connect() as conn:
        results = keyword_search(conn, query, limit)
    typer.echo(json.dumps(results, indent=2))


@app.command("evaluate")
def evaluate_command(path: Path = Path("data/eval_queries.json"), k: int = 5,
                     output: Path = Path("reports/keyword_metrics.json")):
    """Evaluate retrieval on labeled queries and write machine-readable metrics."""
    with connect() as conn:
        report = evaluate(path, lambda query, limit: keyword_search(conn, query, limit), k)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(json.dumps(report["metrics"], indent=2))
    typer.echo(f"Saved {output}")


if __name__ == "__main__":
    app()
