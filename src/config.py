"""Data locations and constants.

The data root is defined in exactly one place. Today that is local disk; if the
Parquet layer ever moves to object storage, this is the only module that has to
change — ingest, DuckDB and Streamlit all read their paths from here.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"

DEFAULT_SEASON = "2025-26"

# Overridable via NBA_LOAD_DATA_DIR. DuckDB reads a local path and an
# "s3://bucket/prefix" URI through the same read_parquet() call, so the layer is
# kept as a string rather than a Path.
DATA_DIR = os.environ.get("NBA_LOAD_DATA_DIR", str(PROJECT_ROOT / "data"))

RAW_DIR = f"{DATA_DIR}/raw"
CURATED_DIR = f"{DATA_DIR}/curated"

PLAYER_TRACK_PARQUET = f"{CURATED_DIR}/player_track.parquet"
GAMES_PARQUET = f"{CURATED_DIR}/games.parquet"


def raw_game_path(game_id: str) -> str:
    """Raw tracking file for one game. Its existence means "already fetched"."""
    return f"{RAW_DIR}/{game_id}.parquet"


def ensure_local_dirs() -> None:
    """Create data/raw and data/curated for local runs; a no-op on object storage."""
    if "://" in DATA_DIR:
        return
    Path(RAW_DIR).mkdir(parents=True, exist_ok=True)
    Path(CURATED_DIR).mkdir(parents=True, exist_ok=True)
