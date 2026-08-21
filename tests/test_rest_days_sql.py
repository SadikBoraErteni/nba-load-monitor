"""sql/40_rest_days.sql and sql/15_players.sql — schedule context and the player dimension."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from tests.conftest import build_frames, make_con

START = dt.date(2025, 10, 20)


def rest_df(con):
    return con.execute("SELECT * FROM player_game_rest ORDER BY game_date").df()


def test_back_to_back_is_flagged(con_factory):
    """Playing on consecutive days is a back-to-back: rest_days = 0."""
    dates = [START, START + dt.timedelta(days=1)]
    df = rest_df(con_factory(dates))

    assert df.iloc[1].rest_days == 0
    assert bool(df.iloc[1].is_back_to_back) is True


def test_one_day_off_is_not_a_back_to_back(con_factory):
    """The empty day counts: Oct 20 and Oct 22 means one day of rest."""
    dates = [START, START + dt.timedelta(days=2)]
    df = rest_df(con_factory(dates))

    assert df.iloc[1].rest_days == 1
    assert bool(df.iloc[1].is_back_to_back) is False


@pytest.mark.parametrize("gap, expected_rest", [(1, 0), (2, 1), (3, 2), (7, 6)])
def test_rest_day_arithmetic(con_factory, gap, expected_rest):
    dates = [START, START + dt.timedelta(days=gap)]
    df = rest_df(con_factory(dates))
    assert df.iloc[1].rest_days == expected_rest


def test_rest_is_unknown_for_the_first_game(con_factory):
    """With no previous game, rest_days is NULL — "rested zero days" would be a claim."""
    dates = [START, START + dt.timedelta(days=2)]
    df = rest_df(con_factory(dates))

    assert pd.isna(df.iloc[0].rest_days)
    assert pd.isna(df.iloc[0].prev_game_date)
    assert pd.isna(df.iloc[0].is_back_to_back)


def test_rest_is_computed_per_player():
    """One player's schedule must not leak into another's (is PARTITION BY right?)."""
    t1, g1 = build_frames([START, START + dt.timedelta(days=1)], person_id=1, team="AAA")
    t2, g2 = build_frames([START + dt.timedelta(days=5)], person_id=2, team="BBB")
    t2 = t2.assign(game_id="0022509999")
    g2 = g2.assign(game_id="0022509999")

    con = make_con(
        pd.concat([t1, t2], ignore_index=True), pd.concat([g1, g2], ignore_index=True)
    )
    df = rest_df(con)

    player2 = df[df.person_id == 2]
    assert len(player2) == 1
    assert pd.isna(player2.iloc[0].rest_days)


# --------------------------------------------------------------------------
# players (the player dimension)
# --------------------------------------------------------------------------


def test_dnp_games_are_not_counted_as_played():
    """The tracking feed also returns rows for players who did not appear.

    Counting those as games would distort per-game averages and weaken the
    minimum-games filter — but the load still has to stay in the series as 0.
    """
    dates = [START, START + dt.timedelta(days=2), START + dt.timedelta(days=4)]
    track, games = build_frames(dates, miles=[2.0, 0.0, 2.5])
    track.loc[1, "minutes_played"] = 0.0  # the middle game is a DNP

    con = make_con(track, games)
    players = con.execute("SELECT * FROM players").df().iloc[0]

    assert players.games_played == 2, "a DNP is not a game played"
    assert players.total_miles == pytest.approx(4.5)
    assert players.avg_minutes == pytest.approx(30.0)
    assert players.first_game_date.date() == dates[0]
    assert players.last_game_date.date() == dates[-1]


def test_players_reports_the_latest_team():
    """For a player traded mid-season, show where they ended up."""
    dates = [START, START + dt.timedelta(days=30)]
    track, games = build_frames(dates)
    track.loc[1, "team_tricode"] = "NEW"
    games.loc[1, "team_tricode"] = "NEW"

    con = make_con(track, games)
    players = con.execute("SELECT * FROM players").df().iloc[0]

    assert players.team_tricode == "NEW"
    assert players.games_played == 2
