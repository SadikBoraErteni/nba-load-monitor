"""Fetch NBA per-game player tracking data and write it to Parquet.

    python -m src.ingest --season 2025-26

Two layers are written:

  data/raw/{game_id}.parquet   Raw tracking, one file per game. Not in git.
                               The presence of a file means "this game was
                               already fetched" — that is the script's ledger,
                               there is no separate state file.
  data/curated/*.parquet       Consolidated, column-selected, minutes-parsed.
                               Committed to git, because Streamlit Community
                               Cloud runs the app straight from the repo.

If the run is interrupted, just run it again: fetched games are skipped.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import boxscoreplayertrackv3, leaguegamelog

from src import config
from src.transform import full_name, parse_minutes

SEASON_TYPES = ["Regular Season", "Playoffs"]

# Tracking columns kept in the curated layer. The endpoint returns 35 columns,
# but this project is about physical load — passes, rebound chances and the rest
# of the box-score-adjacent fields are deliberately left behind.
TRACK_COLUMNS = [
    "game_id",
    "person_id",
    "player_name",
    "team_tricode",
    "minutes_played",
    "avg_speed_mph",
    "distance_miles",
]


def fetch_game_index(season: str) -> pd.DataFrame:
    """Season schedule, one row per team per game (so two rows per game)."""
    frames = []
    for season_type in SEASON_TYPES:
        log = leaguegamelog.LeagueGameLog(
            season=season, season_type_all_star=season_type, timeout=60
        )
        df = log.get_data_frames()[0]
        if df.empty:
            print(f"  warning: {season_type} returned no rows")
            continue
        df = df[["GAME_ID", "GAME_DATE", "TEAM_ID", "TEAM_ABBREVIATION", "MATCHUP", "WL"]]
        df.columns = ["game_id", "game_date", "team_id", "team_tricode", "matchup", "wl"]
        df["season_type"] = season_type
        frames.append(df)
        print(f"  {season_type}: {df.game_id.nunique()} games")

    games = pd.concat(frames, ignore_index=True)
    games["season"] = season
    games["game_date"] = pd.to_datetime(games["game_date"]).dt.date
    return games


def fetch_game_tracking(game_id: str, retries: int = 3) -> pd.DataFrame:
    """Player-level tracking rows for one game, retried with backoff on failure."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            endpoint = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                game_id=game_id, timeout=60
            )
            return endpoint.get_data_frames()[0]
        except Exception as exc:  # network, timeout, schema — all worth retrying
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"could not fetch {game_id}: {last_error}")


def ingest_games(game_ids: list[str], sleep: float) -> list[str]:
    """Fetch missing games in order, skipping what is already on disk.

    Returns the ids that failed so a rerun can pick them up.
    """
    todo = [g for g in game_ids if not Path(config.raw_game_path(g)).exists()]
    already = len(game_ids) - len(todo)
    print(f"{len(game_ids)} games | {already} already on disk | {len(todo)} to fetch")
    if not todo:
        return []

    failed: list[str] = []
    started = time.time()
    for i, game_id in enumerate(todo, start=1):
        try:
            df = fetch_game_tracking(game_id)
            df.to_parquet(config.raw_game_path(game_id), index=False)
        except Exception as exc:
            print(f"  ERROR {game_id}: {exc}")
            failed.append(game_id)

        if i % 25 == 0 or i == len(todo):
            elapsed = time.time() - started
            remaining = (len(todo) - i) * (elapsed / i)
            print(
                f"  {i}/{len(todo)} | {elapsed/60:.1f} min elapsed | "
                f"~{remaining/60:.1f} min left | {len(failed)} failed",
                flush=True,
            )
        time.sleep(sleep)

    return failed


def consolidate() -> pd.DataFrame:
    """Fold the raw per-game files into a single curated Parquet.

    The only transformations here are column selection and minutes parsing.
    No load or ACWR arithmetic — that belongs to SQL.
    """
    files = sorted(Path(config.RAW_DIR).glob("*.parquet"))
    if not files:
        raise SystemExit("data/raw is empty — run the ingest first")

    raw = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    out = pd.DataFrame(
        {
            "game_id": raw["gameId"].astype(str),
            "person_id": raw["personId"].astype("int64"),
            "player_name": [
                full_name(f, l) for f, l in zip(raw["firstName"], raw["familyName"])
            ],
            "team_tricode": raw["teamTricode"].astype(str),
            "minutes_played": [parse_minutes(m) for m in raw["minutes"]],
            "avg_speed_mph": pd.to_numeric(raw["speed"], errors="coerce").fillna(0.0),
            "distance_miles": pd.to_numeric(raw["distance"], errors="coerce").fillna(0.0),
        }
    )[TRACK_COLUMNS]

    out.to_parquet(config.PLAYER_TRACK_PARQUET, index=False)
    size_mb = Path(config.PLAYER_TRACK_PARQUET).stat().st_size / 1e6
    print(
        f"curated/player_track.parquet: {len(out):,} rows, "
        f"{out.person_id.nunique():,} players, {out.game_id.nunique():,} games, "
        f"{size_mb:.2f} MB"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default=config.DEFAULT_SEASON)
    parser.add_argument(
        "--sleep", type=float, default=0.6, help="delay between requests, seconds"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after N games (for smoke runs)"
    )
    parser.add_argument(
        "--consolidate-only",
        action="store_true",
        help="skip fetching, just rebuild the curated layer from raw",
    )
    args = parser.parse_args()

    config.ensure_local_dirs()

    if not args.consolidate_only:
        print(f"[1/3] fetching {args.season} schedule")
        games = fetch_game_index(args.season)
        games.to_parquet(config.GAMES_PARQUET, index=False)
        print(f"  curated/games.parquet: {len(games):,} rows")

        game_ids = sorted(games.game_id.unique())
        if args.limit:
            game_ids = game_ids[: args.limit]

        print(f"[2/3] fetching tracking data (sleep={args.sleep}s)")
        failed = ingest_games(game_ids, args.sleep)
        if failed:
            print(f"  {len(failed)} games could not be fetched: {failed[:10]}")
            print("  rerunning will retry only those")

    print("[3/3] writing curated layer")
    consolidate()
    print("done")


if __name__ == "__main__":
    main()
