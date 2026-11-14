"""Project configuration and environment helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/arm_metadata")


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_embedding_model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")


def get_embedding_device() -> str:
    value = os.environ.get("EMBEDDING_DEVICE", "cpu").strip().lower()
    if not value or value == "auto":
        return "cpu"
    return value


def get_embedding_batch_size() -> int:
    value = os.environ.get("EMBEDDING_BATCH_SIZE", "32")
    try:
        batch_size = int(value)
    except ValueError:
        batch_size = 32
    return max(1, batch_size)


def get_embedding_dimension() -> int:
    value = os.environ.get("EMBEDDING_DIMENSION", "384")
    try:
        dimension = int(value)
    except ValueError:
        dimension = 384
    return max(1, dimension)
