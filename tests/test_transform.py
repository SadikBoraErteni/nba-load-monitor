"""parse_minutes and full_name — the pure field-to-number functions."""

import pytest

from src.transform import full_name, parse_minutes


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("41:45", 41.75),
        ("48:53", 48 + 53 / 60),
        ("0:00", 0.0),
        ("7:30", 7.5),
        ("  12:06  ", 12.1),
        # Some endpoints in the same v3 family return ISO 8601 durations.
        ("PT41M45.00S", 41.75),
        ("PT36M00.00S", 36.0),
        ("PT0M30.00S", 0.5),
    ],
)
def test_parse_minutes_formats(raw, expected):
    assert parse_minutes(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "   ", None, "DNP", "garbage", float("nan")])
def test_parse_minutes_returns_zero_for_missing_or_malformed(raw):
    """A player who never took the floor has zero load, not unknown load.

    The daily series behind ACWR depends on this: those zeros are what let rest
    actually pull chronic load down.
    """
    assert parse_minutes(raw) == 0.0


def test_parse_minutes_passes_through_numeric_input():
    assert parse_minutes(7.5) == 7.5
    assert parse_minutes(0) == 0.0


def test_parse_minutes_does_not_round_seconds_into_a_minute():
    assert parse_minutes("10:59") < 11.0
    assert parse_minutes("10:59") > 10.98


def test_full_name():
    assert full_name("Alperen", "Sengun") == "Alperen Sengun"
    assert full_name(None, "Sengun") == "Sengun"
    assert full_name("Nikola", None) == "Nikola"
    assert full_name(None, None) == ""
    assert full_name("  Kevin  ", " Durant ") == "Kevin Durant"
