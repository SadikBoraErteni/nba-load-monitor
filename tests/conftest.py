"""Test scaffolding: build a synthetic schedule and run the REAL sql/ files.

The key decision here: the tests do not exercise a Python re-implementation of
ACWR. They read sql/30_acwr.sql off disk and execute it. When a test passes, the
SQL the app runs and the SQL in the repository are guaranteed to be the same
thing — a parallel implementation could drift apart in silence.

The one exception is 00_views.sql, which is skipped. Its only job is to point the
views at Parquet; the tests register tables under the same two names instead.
"""

from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd
import pytest

from src import db

# The whole view chain except the data source, which the test supplies itself.
DERIVED_VIEWS = [name for name in db.VIEW_FILES if name != "00_views"]


def build_frames(
    game_dates: list[dt.date],
    miles: float | list[float] = 2.0,
    person_id: int = 1,
    player_name: str = "Test Player",
    team: str = "TST",
    minutes: float = 30.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a one-player season that plays on exactly the given dates."""
    if isinstance(miles, (int, float)):
        miles = [float(miles)] * len(game_dates)
    assert len(miles) == len(game_dates)

    game_ids = [f"002250{i:04d}" for i in range(len(game_dates))]

    track = pd.DataFrame(
        {
            "game_id": game_ids,
            "person_id": person_id,
            "player_name": player_name,
            "team_tricode": team,
            "minutes_played": minutes,
            "avg_speed_mph": 4.0,
            "distance_miles": miles,
        }
    )
    games = pd.DataFrame(
        {
            "game_id": game_ids,
            "game_date": game_dates,
            "team_id": 1610612700,
            "team_tricode": team,
            "matchup": "TST vs. OPP",
            "wl": "W",
            "season_type": "Regular Season",
            "season": "2025-26",
        }
    )
    return track, games


def make_con(track: pd.DataFrame, games: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    """Load the synthetic data and build the real view chain on top of it."""
    con = duckdb.connect()
    con.register("track_src", track)
    con.register("games_src", games)
    con.execute("CREATE TABLE player_track_raw AS SELECT * FROM track_src")
    # game_date must be a DATE: pandas hands over a TIMESTAMP, and the daily
    # calendar join relies on date equality.
    con.execute(
        "CREATE TABLE games_raw AS "
        "SELECT * REPLACE (game_date::DATE AS game_date) FROM games_src"
    )
    for name in DERIVED_VIEWS:
        con.execute(db.sql_text(name))
    return con


@pytest.fixture
def con_factory():
    """Lets each test declare its own schedule."""

    def _factory(game_dates, **kwargs):
        return make_con(*build_frames(game_dates, **kwargs))

    return _factory


def weekly_rhythm(start: dt.date, weeks: int, weekdays=(0, 2, 4)) -> list[dt.date]:
    """A fixed weekly schedule (Mon/Wed/Fri by default) — the steady-state case.

    A fixed rhythm pins ACWR to exactly 1.0, because any 7 consecutive days
    contain each weekday exactly once: 3 games per acute window, 12 per chronic
    window. The expected value is arithmetic, not a guess.
    """
    days = []
    monday = start - dt.timedelta(days=start.weekday())
    for week in range(weeks):
        for wd in weekdays:
            days.append(monday + dt.timedelta(days=week * 7 + wd))
    return [d for d in days if d >= start]
