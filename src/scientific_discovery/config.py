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
