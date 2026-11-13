"""Deterministic PostgreSQL full-text keyword search."""


def keyword_search(conn, query: str, limit: int = 10) -> list[dict]:
    if not query.strip():
        return []
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT dataset_id, title, description, source, landing_page,
                   ts_rank_cd(search_vector, websearch_to_tsquery('english', %(query)s)) AS score
            FROM datasets
            WHERE search_vector @@ websearch_to_tsquery('english', %(query)s)
            ORDER BY score DESC, dataset_id ASC
            LIMIT %(limit)s
        """, {"query": query, "limit": limit})
        columns = ("dataset_id", "title", "description", "source", "landing_page", "score")
        return [dict(zip(columns, row)) for row in cur.fetchall()]
