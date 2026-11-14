"""Deterministic metadata text and embedding utilities for semantic retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .config import (
    get_embedding_batch_size,
    get_embedding_device,
    get_embedding_dimension,
    get_embedding_model_name,
)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _record_to_mapping(record: Any) -> Mapping[str, Any]:
    if isinstance(record, Mapping):
        return record
    if hasattr(record, "model_dump"):
        return record.model_dump()
    if hasattr(record, "dict"):
        return record.dict()
    raise TypeError(f"Unsupported record type for embedding: {type(record)!r}")


def _textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_textify(item) for item in value)
    if isinstance(value, Mapping):
        return " ".join(_textify(v) for v in value.values())
    return str(value)


def build_metadata_text(record: Any) -> str:
    """Build a deterministic text representation for a scientific metadata record."""
    record_mapping = _record_to_mapping(record)
    title = _textify(record_mapping.get("title") or record_mapping.get("dataset_name") or record_mapping.get("name") or "")
    description = _textify(record_mapping.get("description") or record_mapping.get("dataset_description") or "")
    source = _textify(record_mapping.get("source") or "")
    source_identifier = _textify(record_mapping.get("source_identifier") or record_mapping.get("dataset_id") or "")
    site_name = _textify(record_mapping.get("site_name") or "")
    site_code = _textify(record_mapping.get("site_code") or "")
    location = _textify(record_mapping.get("location") or "")
    keywords = _textify(record_mapping.get("keywords") or [])
    raw_metadata = record_mapping.get("raw_metadata") or {}
    raw_keywords = _textify(raw_metadata.get("keywords") or raw_metadata.get("scientific_keywords") or [])
    instrument = _textify(raw_metadata.get("instrument_name") or raw_metadata.get("instrument_class_name_text") or raw_metadata.get("instrument") or "")

    variable_names: list[str] = []
    for variable in record_mapping.get("variables") or []:
        if isinstance(variable, Mapping):
            name = variable.get("name") or variable.get("variable_name")
            if name:
                variable_names.append(_textify(name))
        else:
            variable_names.append(_textify(variable))

    variable_text = " ".join(variable_names)
    values = [
        title,
        description,
        source,
        source_identifier,
        site_name,
        site_code,
        location,
        keywords,
        raw_keywords,
        instrument,
        variable_text,
    ]
    normalized = " ".join(part for part in values if part and str(part).strip())
    return " ".join(normalized.split())


def _stable_vector_from_text(text: str, dimension: int) -> list[float]:
    slug = re.findall(r"[A-Za-z0-9]+", text.lower())
    if not slug:
        return [0.0 for _ in range(dimension)]

    vector = [0.0 for _ in range(dimension)]
    for token in slug:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        magnitude = int.from_bytes(digest[:8], "big") / float(2**64)
        scalar = (magnitude * 2.0) - 1.0
        slot = int.from_bytes(digest[8:12], "big") % dimension
        vector[slot] += scalar

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in range(dimension)]
    return [value / norm for value in vector]


def _encode_with_sentence_transformers(texts: Sequence[str], model_name: str, device: str, batch_size: int) -> list[list[float]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return []

    model = SentenceTransformer(model_name, device=device)
    embeddings = model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True)
    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return list(embeddings)


def generate_embeddings(texts: Sequence[str], model_name: str | None = None, device: str | None = None, batch_size: int | None = None) -> list[list[float]]:
    """Generate deterministic embeddings or fall back to sentence-transformers when available."""
    model_name = model_name or get_embedding_model_name()
    device = (device or get_embedding_device()).strip().lower() if (device or get_embedding_device()) else "cpu"
    if device in {"", "auto"}:
        device = "cpu"
    batch_size = batch_size or get_embedding_batch_size()
    if not texts:
        return []

    sentence_transformers_embeddings = _encode_with_sentence_transformers(texts, model_name, device, batch_size)
    if sentence_transformers_embeddings:
        return sentence_transformers_embeddings

    dimension = get_embedding_dimension()
    return [_stable_vector_from_text(text, dimension) for text in texts]


def to_retrieval_result(record: Mapping[str, Any], rank: int, *, lexical_score: float | None = None, semantic_score: float | None = None, rrf_score: float | None = None, source_url: str | None = None) -> dict[str, Any]:
    dataset_id = record.get("dataset_id") or record.get("source_identifier") or record.get("id")
    return {
        "dataset_id": dataset_id,
        "title": record.get("title") or record.get("dataset_name") or record.get("name"),
        "description": record.get("description") or "",
        "source": record.get("source"),
        "source_identifier": record.get("source_identifier") or dataset_id,
        "site_code": record.get("site_code"),
        "site_name": record.get("site_name"),
        "source_url": source_url or record.get("source_url") or record.get("landing_page"),
        "rank": rank,
        "lexical_score": lexical_score,
        "semantic_score": semantic_score,
        "rrf_score": rrf_score,
        "provenance": {
            "source": record.get("source"),
            "source_identifier": record.get("source_identifier") or dataset_id,
            "source_url": source_url or record.get("source_url") or record.get("landing_page"),
            "raw_metadata": record.get("raw_metadata") or {},
        },
    }


def reciprocal_rank_fusion(lexical_results: Iterable[Mapping[str, Any]], semantic_results: Iterable[Mapping[str, Any]], k: int = 60, rrf_constant: int = 60) -> list[dict[str, Any]]:
    """Combine lexical and semantic rankings using reciprocal rank fusion."""
    lexical_list = list(lexical_results)
    semantic_list = list(semantic_results)

    fused_scores: dict[str, tuple[float, str, str | None, str | None]] = {}

    for rank, item in enumerate(lexical_list, start=1):
        dataset_id = item.get("dataset_id") or item.get("source_identifier") or item.get("id")
        if dataset_id is None:
            continue
        fused_scores.setdefault(dataset_id, (0.0, dataset_id, item.get("source"), item.get("source_url")))
        score, _dataset_id, source, source_url = fused_scores[dataset_id]
        fused_scores[dataset_id] = (score + (1.0 / (rrf_constant + rank)), dataset_id, source or item.get("source"), source_url or item.get("source_url"))

    for rank, item in enumerate(semantic_list, start=1):
        dataset_id = item.get("dataset_id") or item.get("source_identifier") or item.get("id")
        if dataset_id is None:
            continue
        fused_scores.setdefault(dataset_id, (0.0, dataset_id, item.get("source"), item.get("source_url")))
        score, _dataset_id, source, source_url = fused_scores[dataset_id]
        fused_scores[dataset_id] = (score + (1.0 / (rrf_constant + rank)), dataset_id, source or item.get("source"), source_url or item.get("source_url"))

    ranked = []
    for dataset_id, (score, _dataset_id, source, source_url) in fused_scores.items():
        ranked.append({
            "dataset_id": dataset_id,
            "source": source,
            "source_url": source_url,
            "score": round(score, 12),
        })

    ranked.sort(key=lambda item: (-item["score"], item["dataset_id"]))
    return ranked
