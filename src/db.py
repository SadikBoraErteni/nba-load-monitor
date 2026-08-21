"""DuckDB layer.

This module is deliberately thin: it opens a connection, runs the files under
sql/, and hands back DataFrames. It contains no arithmetic of its own — all of
the load, ACWR and rest-day logic lives in .sql files, because having that SQL
readable in the repository is one of the goals of this project.

    from src import db
    con = db.connect()
    df = db.query(con, "60_player_timeline", {"person_id": 1630578})
"""

from __future__ import annotations

import argparse
from functools import lru_cache

import duckdb
import pandas as pd

from src import config

# Executed in this order during bootstrap; each view builds on the previous one,
# so the order matters.
VIEW_FILES = [
    "00_views",
    "10_player_game_load",
    "15_players",
    "20_player_daily_load",
    "30_acwr",
    "40_rest_days",
]


@lru_cache(maxsize=None)
def sql_text(name: str) -> str:
    """Contents of sql/<name>.sql."""
    path = config.SQL_DIR / f"{name}.sql"
    if not path.exists():
        raise FileNotFoundError(f"no such SQL file: {path}")
    return path.read_text(encoding="utf-8")


def bootstrap(
    con: duckdb.DuckDBPyConnection,
    player_track: str | None = None,
    games: str | None = None,
) -> None:
    """Build the view chain.

    Without arguments the Parquet paths from config are used. The test suite
    skips this step and registers tables under the same names instead, so the
    SQL under test is byte-for-byte the SQL the app runs.
    """
    track_path = player_track or config.PLAYER_TRACK_PARQUET
    games_path = games or config.GAMES_PARQUET

    for name in VIEW_FILES:
        script = sql_text(name)
        script = script.replace("{player_track}", track_path).replace(
            "{games}", games_path
        )
        # DuckDB parses multi-statement scripts itself; splitting on ';' by hand
        # would also cut semicolons that appear inside comments.
        con.execute(script)


def connect(**bootstrap_kwargs) -> duckdb.DuckDBPyConnection:
    """In-memory connection with the views in place. Parquet is read where it lies."""
    con = duckdb.connect()
    bootstrap(con, **bootstrap_kwargs)
    return con


def query(
    con: duckdb.DuckDBPyConnection, name: str, params: dict | None = None
) -> pd.DataFrame:
    """Run sql/<name>.sql and return the result as a DataFrame."""
    return con.execute(sql_text(name), params or {}).df()


def check() -> int:
    """Smoke test: do the views build, and are the numbers plausible?"""
    con = connect()

    counts = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM player_track_raw)  AS track_rows,
            (SELECT COUNT(*) FROM games_raw)         AS game_rows,
            (SELECT COUNT(*) FROM player_game_load)  AS load_rows,
            (SELECT COUNT(*) FROM players)           AS players,
            (SELECT COUNT(*) FROM player_daily_load) AS daily_rows,
            (SELECT COUNT(*) FROM player_acwr WHERE acwr IS NOT NULL) AS acwr_rows
        """
    ).df()
    print(counts.to_string(index=False))

    stats = con.execute(
        """
        SELECT
            ROUND(MIN(acwr), 3) AS min_acwr,
            ROUND(AVG(acwr), 3) AS avg_acwr,
            ROUND(MAX(acwr), 3) AS max_acwr,
            COUNT(*) FILTER (WHERE acwr > 1.5) AS high_days
        FROM player_acwr WHERE acwr IS NOT NULL
        """
    ).df()
    print(stats.to_string(index=False))

    problems = []
    if counts.track_rows[0] != counts.load_rows[0]:
        problems.append(
            f"join lost rows: {counts.track_rows[0]} tracking -> {counts.load_rows[0]} load"
        )
    if counts.acwr_rows[0] == 0:
        problems.append("no ACWR at all — a season cannot be shorter than 28 days")
    if len(stats) and stats.max_acwr[0] is not None and stats.max_acwr[0] > 4.0:
        # 4.0 is the mathematical ceiling: the acute window is a subset of the
        # chronic one, which is divided by four. Anything above means a bug.
        problems.append(f"ACWR above its ceiling of 4.0: {stats.max_acwr[0]}")

    for p in problems:
        print(f"PROBLEM: {p}")
    if not problems:
        print("smoke OK")
    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run the smoke test")
    args = parser.parse_args()
    raise SystemExit(check() if args.check else 0)
