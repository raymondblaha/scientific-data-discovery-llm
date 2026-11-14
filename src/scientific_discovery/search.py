"""Search utilities for the metadata discovery system.

This module contains the canonical search logic used by PostgreSQL-backed ingestion and
compatibility imports in the legacy app package.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row


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
