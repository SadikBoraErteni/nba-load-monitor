"""Pure functions that turn raw NBA tracking fields into usable numbers.

Everything here is side-effect free and directly testable. The actual metrics —
ACWR, rest days — live in SQL; this module only produces the clean numbers that
SQL expects.
"""

from __future__ import annotations

import re

# boxscoreplayertrackv3 returns minutes as "41:45" (mm:ss). Other endpoints in
# the same v3 family return ISO 8601 durations ("PT41M45.00S"), so both are
# accepted here — a format surprise should not take down a whole season's ingest.
_CLOCK_RE = re.compile(r"^\s*(\d+):(\d{1,2}(?:\.\d+)?)\s*$")
_ISO_RE = re.compile(r"^\s*PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?\s*$", re.IGNORECASE)


def parse_minutes(value) -> float:
    """Convert time played to decimal minutes.

    >>> parse_minutes("41:45")
    41.75

    DNP rows and missing values return 0.0: if a player never took the floor
    their load is zero, not unknown. The daily series behind ACWR depends on
    those zeros being real.
    """
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        # Already numeric (NaN included) — collapse NaN to zero.
        return float(value) if value == value else 0.0

    text = str(value).strip()
    if not text:
        return 0.0

    match = _CLOCK_RE.match(text)
    if match:
        return int(match.group(1)) + float(match.group(2)) / 60.0

    match = _ISO_RE.match(text)
    if match and (match.group(1) or match.group(2)):
        minutes = int(match.group(1)) if match.group(1) else 0
        seconds = float(match.group(2)) if match.group(2) else 0.0
        return minutes + seconds / 60.0

    # Unrecognised format. Returning 0 makes the data look cleaner than it is,
    # but failing the whole season over one malformed row is worse.
    return 0.0


def full_name(first: str | None, family: str | None) -> str:
    """v3 splits the name in two; the UI and all grouping want one string."""
    parts = [p.strip() for p in (first, family) if p and str(p).strip()]
    return " ".join(parts)
