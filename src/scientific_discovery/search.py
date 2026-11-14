"""Search utilities for the metadata discovery system.

This module contains the canonical search logic used by PostgreSQL-backed ingestion and
compatibility imports in the legacy app package.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .embeddings import (
    build_metadata_text,
    generate_embeddings,
    reciprocal_rank_fusion,
    to_retrieval_result,
)


def _parse_iso(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def filter_date_overlap(record: dict[str, Any], query_start: str | date | None, query_end: str | date | None) -> tuple[str, str | None]:
    record_start = _parse_iso(record.get("start_date"))
    record_end = _parse_iso(record.get("end_date"))
    q_start = _parse_iso(query_start)
    q_end = _parse_iso(query_end)

    if q_start is None and q_end is None:
        return ("unknown", "query date range missing")
    if record_start is None or record_end is None:
        return ("unknown", "record date coverage missing")
    if q_start is not None and q_end is not None:
        if max(record_start, q_start) <= min(record_end, q_end):
            return ("overlap", "date overlap")
        return ("no_overlap", "no date overlap")
    if q_start is not None and record_end >= q_start:
        return ("overlap", "date overlap")
    if q_end is not None and record_start <= q_end:
        return ("overlap", "date overlap")
    return ("no_overlap", "no date overlap")


def _table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (table_name,),
        )
        return bool(cur.fetchone()[0])


def search_records(conn: psycopg.Connection, keyword: str, start_date: str | None = None, end_date: str | None = None, site_code: str | None = None, site_name: str | None = None, source: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    query = (keyword or "").strip()
    if not query:
        return []

    if _table_exists(conn, "dataset_records"):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dataset_records")
            columns = [column[0] for column in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        filtered: list[dict[str, Any]] = []
        for row in rows:
            haystack = " ".join(
                filter(
                    None,
                    [
                        row.get("title") or "",
                        row.get("description") or "",
                        row.get("source") or "",
                        row.get("site_name") or "",
                        row.get("site_code") or "",
                        json.dumps(row.get("raw_metadata") or {}, sort_keys=True),
                    ],
                )
            ).lower()
            if query.lower() not in haystack:
                continue
            if site_code and (row.get("site_code") or "") != site_code:
                continue
            if site_name and (row.get("site_name") or "") != site_name:
                continue
            if source and (row.get("source") or "") != source:
                continue
            if start_date or end_date:
                status, _ = filter_date_overlap(row, start_date, end_date)
                if status == "no_overlap":
                    continue
                row["date_status"] = status
            else:
                row["date_status"] = "unknown"
            filtered.append(row)
            if len(filtered) >= limit:
                break
        return filtered[:limit]

    clauses = ["search_vector @@ websearch_to_tsquery('english', %s)"]
    params: list[Any] = [query]
    if source:
        clauses.append("source = %s")
        params.append(source)
    if site_code:
        clauses.append("site_code = %s")
        params.append(site_code)
    if site_name:
        clauses.append("site_name = %s")
        params.append(site_name)

    sql = f"""
        SELECT dataset_id, title, description, source, landing_page,
               source_identifier, source_url, site_code, site_name,
               start_date, end_date, synthetic,
               ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS score
        FROM datasets
        WHERE {' AND '.join(clauses)}
        ORDER BY score DESC, dataset_id ASC
        LIMIT %s
    """
    params.extend([query, limit])

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if start_date or end_date:
            status, _ = filter_date_overlap(row, start_date, end_date)
            if status == "no_overlap":
                continue
            row["date_status"] = status
        else:
            row["date_status"] = "unknown"
        filtered.append(dict(row))
        if len(filtered) >= limit:
            break
    return filtered


def keyword_search(conn, query: str, limit: int = 10, source: str | None = None, site_code: str | None = None, site_name: str | None = None) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    if not _table_exists(conn, "datasets"):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dataset_records")
            columns = [column[0] for column in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        filtered = []
        requested = query.lower().strip()
        for row in rows:
            haystack = " ".join(
                filter(None, [row.get("title") or "", row.get("description") or "", row.get("source") or "", row.get("site_name") or "", row.get("site_code") or "", json.dumps(row.get("raw_metadata") or {}, sort_keys=True)])
            ).lower()
            if requested not in haystack:
                continue
            if source and (row.get("source") or "") != source:
                continue
            if site_code and (row.get("site_code") or "") != site_code:
                continue
            if site_name and (row.get("site_name") or "") != site_name:
                continue
            filtered.append({
                "dataset_id": row.get("dataset_id"),
                "title": row.get("title"),
                "description": row.get("description"),
                "source": row.get("source"),
                "landing_page": row.get("landing_page"),
                "source_identifier": row.get("source_identifier"),
                "source_url": row.get("source_url"),
                "site_code": row.get("site_code"),
                "site_name": row.get("site_name"),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "synthetic": row.get("synthetic"),
                "score": 1.0,
            })
            if len(filtered) >= limit:
                break
        return filtered

    clauses = ["search_vector @@ websearch_to_tsquery('english', %s)"]
    params: list[Any] = [query, query]

    if source:
        clauses.append("source = %s")
        params.append(source)
    if site_code:
        clauses.append("site_code = %s")
        params.append(site_code)
    if site_name:
        clauses.append("site_name = %s")
        params.append(site_name)

    sql = f"""
        SELECT dataset_id, title, description, source, landing_page,
               source_identifier, source_url, site_code, site_name,
               start_date, end_date, synthetic,
               ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS score
        FROM datasets
        WHERE {' AND '.join(clauses)}
        ORDER BY score DESC, dataset_id ASC
        LIMIT %s
    """
    params.append(limit)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def semantic_search(conn: psycopg.Connection, query: str, limit: int = 10, source: str | None = None, site_code: str | None = None, site_name: str | None = None, model_name: str | None = None, device: str | None = None) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    try:
        register_vector(conn)
    except (AttributeError, TypeError, ValueError):
        pass

    if not _table_exists(conn, "dataset_embeddings"):
        return []

    query_vector = Vector(generate_embeddings([query], model_name=model_name, device=device)[0])
    clauses = ["1 = 1"]
    if source:
        clauses.append("d.source = %s")
    if site_code:
        clauses.append("d.site_code = %s")
    if site_name:
        clauses.append("d.site_name = %s")

    sql = f"""
        SELECT d.dataset_id, d.title, d.description, d.source, d.landing_page,
               d.source_identifier, d.source_url, d.site_code, d.site_name,
               d.start_date, d.end_date, d.synthetic,
               1 - (e.embedding <=> %s) AS similarity
        FROM dataset_embeddings e
        JOIN datasets d ON d.dataset_id = e.dataset_id
        WHERE {' AND '.join(clauses)}
        ORDER BY e.embedding <=> %s
        LIMIT %s
    """
    # param order must match placeholder positions
    param_values: list[Any] = [query_vector]
    if source is not None:
        param_values.append(source)
    if site_code is not None:
        param_values.append(site_code)
    if site_name is not None:
        param_values.append(site_name)
    param_values.extend([query_vector, limit])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, param_values)
        rows = cur.fetchall()

    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        record = dict(row)
        score = float(record.get("similarity", 0.0) or 0.0)
        record["score"] = score
        record["text"] = build_metadata_text(record)
        structured = to_retrieval_result(record, index, semantic_score=score, source_url=record.get("source_url") or record.get("landing_page"))
        structured["score"] = score
        structured["text"] = record["text"]
        results.append(structured)
    return results


def hybrid_search(conn: psycopg.Connection, query: str, limit: int = 10, source: str | None = None, site_code: str | None = None, site_name: str | None = None, rrf_constant: int = 60, model_name: str | None = None, device: str | None = None) -> list[dict[str, Any]]:
    lexical_results = keyword_search(conn, query, limit=max(limit, 20), source=source, site_code=site_code, site_name=site_name)
    semantic_results = semantic_search(conn, query, limit=max(limit, 20), source=source, site_code=site_code, site_name=site_name, model_name=model_name, device=device)
    fused = reciprocal_rank_fusion(lexical_results, semantic_results, k=limit, rrf_constant=rrf_constant)

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, item in enumerate(fused[:limit], start=1):
        dataset_id = item["dataset_id"]
        if dataset_id in seen:
            continue
        seen.add(dataset_id)

        record = {
            "dataset_id": dataset_id,
            "source": item.get("source"),
            "source_identifier": dataset_id,
            "source_url": item.get("source_url"),
            "rank": rank,
            "rrf_score": item["score"],
            "score": item["score"],
            "provenance": {
                "source": item.get("source"),
                "source_identifier": dataset_id,
                "source_url": item.get("source_url"),
            },
        }

        for candidate in lexical_results + semantic_results:
            candidate_id = candidate.get("dataset_id") or candidate.get("source_identifier") or candidate.get("id")
            if candidate_id == dataset_id:
                record.update({
                    "title": candidate.get("title"),
                    "description": candidate.get("description") or "",
                    "site_code": candidate.get("site_code"),
                    "site_name": candidate.get("site_name"),
                    "lexical_score": candidate.get("score") if candidate in lexical_results else None,
                    "semantic_score": candidate.get("score") if candidate in semantic_results else None,
                })
                break

        output.append(record)
    return output
