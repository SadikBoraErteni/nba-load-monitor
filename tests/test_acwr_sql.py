"""Behaviour tests for sql/20_player_daily_load.sql and sql/30_acwr.sql.

The metric lives in SQL, so the tests run SQL (see conftest).

The scenarios use a fixed weekly rhythm on purpose: because any 7 consecutive
days contain each weekday exactly once, the expected ACWR is not an estimate but
arithmetic that lands exactly on 1.0.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.conftest import weekly_rhythm

START = dt.date(2025, 10, 20)  # a Monday
MILES = 2.0


def acwr_df(con):
    return con.execute("SELECT * FROM player_acwr ORDER BY load_date").df()


# --------------------------------------------------------------------------
# The daily series: the DNP = 0 rule
# --------------------------------------------------------------------------


def test_daily_series_has_no_gaps(con_factory):
    """One row per calendar day, not one row per game day."""
    dates = weekly_rhythm(START, weeks=6)
    con = con_factory(dates, miles=MILES)
    df = con.execute("SELECT * FROM player_daily_load ORDER BY load_date").df()

    expected_days = (dates[-1] - dates[0]).days + 1
    assert len(df) == expected_days
    assert df.load_date.is_monotonic_increasing
    assert df.load_date.diff().dropna().dt.days.eq(1).all(), "gap in the calendar"


def test_days_without_a_game_carry_zero_load(con_factory):
    """No game that day means load = 0, not a missing row."""
    dates = weekly_rhythm(START, weeks=6)
    con = con_factory(dates, miles=MILES)
    df = con.execute("SELECT * FROM player_daily_load").df()

    off_days = df[df.games_played == 0]
    assert len(off_days) > 0
    assert (off_days.load_miles == 0.0).all()
    assert df[df.games_played > 0].load_miles.eq(MILES).all()
    assert df.load_miles.sum() == pytest.approx(MILES * len(dates))


def test_calendar_starts_at_the_players_first_game(con_factory):
    """Not at the start of the season.

    Back-filling zeros to opening night for a player who joined in February
    would depress their chronic load and inflate their ACWR.
    """
    dates = weekly_rhythm(START, weeks=4)
    con = con_factory(dates, miles=MILES)
    df = con.execute(
        "SELECT MIN(load_date) AS first, MAX(load_date) AS last FROM player_daily_load"
    ).df()

    assert df["first"][0].date() == dates[0]
    assert df["last"][0].date() == dates[-1]


# --------------------------------------------------------------------------
# ACWR arithmetic
# --------------------------------------------------------------------------


def test_steady_workload_gives_acwr_of_one(con_factory):
    """Fixed weekly rhythm -> acute (3 games) = chronic (12 games / 4) -> 1.0."""
    con = con_factory(weekly_rhythm(START, weeks=12), miles=MILES)
    df = acwr_df(con)
    computed = df[df.acwr.notna()]

    assert len(computed) > 0
    assert computed.acwr.sub(1.0).abs().max() < 1e-9
    assert computed.acute_7d.sub(3 * MILES).abs().max() < 1e-9
    assert computed.chronic_28d.sub(12 * MILES / 4).abs().max() < 1e-9


def test_no_acwr_during_the_first_28_days(con_factory):
    """The warm-up window.

    Dividing by a half-filled chronic window would hand every player a fake 2-3
    in their opening weeks — the quiet, classic failure mode.
    """
    con = con_factory(weekly_rhythm(START, weeks=12), miles=MILES)
    df = acwr_df(con)

    assert df[df.day_index < 28].acwr.isna().all()
    assert df[df.day_index < 28].chronic_28d.isna().all()
    assert df[df.day_index == 28].acwr.notna().all()
    # Acute load is still computed during warm-up; only the ratio is withheld.
    assert df[df.day_index >= 7].acute_7d.notna().all()


def test_acwr_equals_acute_over_chronic(con_factory):
    """The published ratio has to agree with the two published components."""
    con = con_factory(weekly_rhythm(START, weeks=10), miles=MILES)
    df = acwr_df(con)
    d = df[df.acwr.notna()]

    assert (d.acute_7d / d.chronic_28d - d.acwr).abs().max() < 1e-9


def test_sudden_congestion_pushes_acwr_up(con_factory):
    """Steady rhythm, then seven games in seven days -> into the danger zone."""
    steady = weekly_rhythm(START, weeks=8)
    congested = [steady[-1] + dt.timedelta(days=i) for i in range(1, 8)]
    con = con_factory(steady + congested, miles=MILES)
    df = acwr_df(con)

    last = df.iloc[-1]
    assert last.acwr > 1.5, f"expected a spike, got {last.acwr}"
    assert last.acwr_band == "high"
    # It was still normal at the end of the steady stretch, so the spike really
    # does come from the congestion and not from the setup.
    steady_end = df[df.load_date.dt.date == steady[-1]].iloc[0]
    assert steady_end.acwr == pytest.approx(1.0)


def test_returning_from_a_long_absence(con_factory):
    """After a layoff, even a normal workload reads as risky.

    This is the whole point of ACWR: the absolute load may be unchanged, but the
    conditioning that used to absorb it is gone.
    """
    before = weekly_rhythm(START, weeks=6)
    comeback_start = before[-1] + dt.timedelta(days=25)
    after = [comeback_start + dt.timedelta(days=i) for i in (0, 2, 4, 7, 9, 11)]
    con = con_factory(before + after, miles=MILES)
    df = acwr_df(con)

    post_return = df[df.load_date.dt.date >= after[2]]
    assert post_return.acwr.max() > 1.5, "the spike on return is not showing"


def test_no_division_when_chronic_load_is_zero(con_factory):
    """28 days with no load makes the ratio undefined — NULL, not an error.

    On day 28 the single game is still sitting in the first slot of the window,
    so chronic load is NOT zero (acwr = 0/0.5 = 0.0, a valid answer). The window
    only empties out on day 29, which is where the guard has to hold.
    """
    con = con_factory([START, START + dt.timedelta(days=50)], miles=MILES)
    df = acwr_df(con)

    empty_window = df[
        (df.day_index >= 29) & (df.load_date.dt.date < START + dt.timedelta(days=50))
    ]
    assert len(empty_window) > 0
    assert empty_window.acwr.isna().all()
    assert empty_window.chronic_28d.eq(0.0).all()

    boundary = df[df.day_index == 28].iloc[0]
    assert boundary.chronic_28d == pytest.approx(MILES / 4)
    assert boundary.acwr == pytest.approx(0.0)

    assert not df.acwr.isin([float("inf"), float("-inf")]).any()


def test_acwr_bands(con_factory):
    """The band label has to follow the ratio."""
    con = con_factory(weekly_rhythm(START, weeks=10), miles=MILES)
    df = acwr_df(con)
    d = df[df.acwr.notna()]

    assert d.acwr_band.eq("normal").all()  # steady rhythm = sweet spot
    assert df[df.acwr.isna()].acwr_band.isna().all()


# --------------------------------------------------------------------------
# Window fill — the easiest part of ACWR to misread
# --------------------------------------------------------------------------


def test_window_game_counts(con_factory):
    """games_7d / games_28d say how solid a base the ratio rests on."""
    con = con_factory(weekly_rhythm(START, weeks=10), miles=MILES)
    df = acwr_df(con)
    d = df[df.day_index >= 28]

    # Fixed rhythm: 3 games per 7 days, 12 per 28 days.
    assert d.games_7d.eq(3).all()
    assert d.games_28d.eq(12).all()


def test_empty_chronic_window_pins_acwr_to_the_ceiling(con_factory):
    """One game in the last 28 days -> ACWR is 4.0 by construction.

    The acute window is a subset of the chronic one and the chronic sum is
    divided by four, so a lone game falling into both windows lands exactly on
    the ceiling. That is an absent baseline, not a spike in workload — the
    league table filters it out via games_28d.
    """
    con = con_factory([START, START + dt.timedelta(days=30)], miles=MILES)
    df = acwr_df(con)
    last = df.iloc[-1]

    assert last.games_28d == 1
    assert last.games_7d == 1
    assert last.acwr == pytest.approx(4.0)


def test_acwr_can_never_exceed_four(con_factory):
    """No schedule, however extreme, can push the ratio past its ceiling."""
    steady = weekly_rhythm(START, weeks=6)
    congested = [steady[-1] + dt.timedelta(days=i) for i in range(1, 8)]
    con = con_factory(steady + congested, miles=[MILES] * len(steady) + [10.0] * 7)
    df = acwr_df(con)

    assert df.acwr.max() <= 4.0 + 1e-9


def test_dnp_days_count_as_zero_games_but_stay_in_the_series(con_factory):
    """A DNP is a day with load, minutes and games all at zero — not a game played.

    games_28d is what the league table uses to decide whether a chronic window is
    real. If DNP rows counted as games, a window carrying no load at all would
    look well populated and the filter would pass players it exists to reject.
    """
    from tests.conftest import build_frames, make_con

    dates = [START, START + dt.timedelta(days=2), START + dt.timedelta(days=4)]
    track, games = build_frames(dates, miles=[2.0, 0.0, 2.5])
    track.loc[1, "minutes_played"] = 0.0  # middle game is a DNP

    con = make_con(track, games)
    daily = con.execute(
        "SELECT * FROM player_daily_load ORDER BY load_date"
    ).df()

    dnp_day = daily[daily.load_date.dt.date == dates[1]].iloc[0]
    assert dnp_day.games_played == 0
    assert dnp_day.load_miles == 0.0
    # The row still exists — the calendar stays gap-free.
    assert len(daily) == (dates[-1] - dates[0]).days + 1
    assert daily.games_played.sum() == 2
