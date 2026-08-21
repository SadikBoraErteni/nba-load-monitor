"""NBA Physical Load Monitor — Streamlit front end.

This file only asks and draws. Every load, ACWR and rest-day calculation lives in
sql/; there is not a single line of metric arithmetic here.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import config, db

st.set_page_config(
    page_title="NBA Physical Load Monitor",
    page_icon="🏀",
    layout="wide",
)

# ACWR bands — the same vocabulary is used in charts, tables and badges.
BAND_LABEL = {
    "high": "High (>1.50)",
    "caution": "Caution (1.30-1.50)",
    "normal": "Normal (0.80-1.30)",
    "low": "Low (<0.80)",
}


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


@st.cache_resource
def get_connection():
    return db.connect()


@st.cache_data(ttl=3600)
def run_query(name: str, params: tuple = ()) -> pd.DataFrame:
    """Run sql/<name>.sql.

    Parameters arrive as (key, value) pairs rather than a dict, because the
    cache key has to be hashable.
    """
    con = get_connection().cursor()
    return db.query(con, name, dict(params))


def data_available() -> bool:
    return (
        Path(config.PLAYER_TRACK_PARQUET).exists()
        and Path(config.GAMES_PARQUET).exists()
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def load_chart(tl: pd.DataFrame, player: str) -> go.Figure:
    """Daily game load as bars, acute/chronic load as lines on a secondary axis.

    Two different units are in play: bars are miles per game, lines are miles per
    week. Sharing one axis would flatten the bars into nothing.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    game_days = tl[tl.games_played > 0]
    fig.add_trace(
        go.Bar(
            x=game_days.load_date,
            y=game_days.load_miles,
            name="Game load (miles)",
            marker_color="#9aa7b8",
            hovertemplate="%{x|%d %b}<br>%{y:.2f} mi<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=tl.load_date,
            y=tl.acute_7d,
            name="Acute (7-day)",
            line=dict(color="#d62728", width=2),
            hovertemplate="%{x|%d %b}<br>acute %{y:.1f} mi<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=tl.load_date,
            y=tl.chronic_28d,
            name="Chronic (28-day avg)",
            line=dict(color="#1f77b4", width=2, dash="dash"),
            hovertemplate="%{x|%d %b}<br>chronic %{y:.1f} mi<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=f"{player} — game load and weekly workload trend",
        height=380,
        margin=dict(t=50, b=30, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hovermode="x unified",
        bargap=0.5,
    )
    fig.update_yaxes(title_text="Miles per game", secondary_y=False)
    fig.update_yaxes(title_text="Miles per week", secondary_y=True, showgrid=False)
    return fig


def acwr_chart(tl: pd.DataFrame) -> go.Figure:
    """ACWR over time, with the sweet spot and the danger zone shaded."""
    fig = go.Figure()

    computed = tl[tl.acwr.notna()]
    if computed.empty:
        fig.add_annotation(
            text="Not enough history for ACWR yet (first 28 days)",
            showarrow=False,
            font=dict(size=14),
        )
        fig.update_layout(height=320)
        return fig

    upper = max(2.6, float(computed.acwr.max()) * 1.1)
    fig.add_hrect(y0=0.8, y1=1.3, fillcolor="#2ca02c", opacity=0.10, line_width=0)
    fig.add_hrect(y0=1.5, y1=upper, fillcolor="#d62728", opacity=0.10, line_width=0)
    fig.add_hline(
        y=1.5,
        line=dict(color="#d62728", width=1, dash="dot"),
        annotation_text="1.50 — workload spike threshold",
        annotation_position="top left",
    )

    fig.add_trace(
        go.Scatter(
            x=computed.load_date,
            y=computed.acwr,
            name="ACWR",
            mode="lines",
            line=dict(color="#222222", width=2),
            hovertemplate="%{x|%d %b %Y}<br>ACWR %{y:.2f}<extra></extra>",
        )
    )

    spikes = computed[computed.acwr > 1.5]
    if not spikes.empty:
        fig.add_trace(
            go.Scatter(
                x=spikes.load_date,
                y=spikes.acwr,
                name="Above threshold",
                mode="markers",
                marker=dict(color="#d62728", size=6),
                hovertemplate="%{x|%d %b %Y}<br>ACWR %{y:.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title="ACWR — acute to chronic workload ratio",
        height=320,
        margin=dict(t=50, b=30, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="ACWR")
    return fig


def games_chart(games: pd.DataFrame) -> go.Figure:
    """Distance per game, with back-to-backs called out."""
    fig = go.Figure()
    b2b = games.is_back_to_back.fillna(False).astype(bool)

    for value, color, label in [
        (False, "#9aa7b8", "Normal rest"),
        (True, "#d62728", "Back-to-back"),
    ]:
        subset = games[b2b == value]
        if subset.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=subset.game_date,
                y=subset.load_miles,
                name=label,
                marker_color=color,
                customdata=subset[["matchup", "rest_days", "minutes_played"]],
                hovertemplate=(
                    "%{x|%d %b}<br>%{customdata[0]}<br>"
                    "%{y:.2f} mi · %{customdata[2]:.0f} min<br>"
                    "rest: %{customdata[1]} days<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="Distance per game — back-to-backs in red",
        height=300,
        margin=dict(t=50, b=30, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        bargap=0.4,
    )
    fig.update_yaxes(title_text="Miles")
    return fig


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


def player_tab() -> None:
    min_games = st.sidebar.slider("Minimum games played to appear in the list", 1, 60, 20)
    options = run_query("90_player_options", (("min_games", min_games),))

    if options.empty:
        st.warning("No player matches this filter.")
        return

    labels = {
        int(r.person_id): f"{r.player_name} ({r.team_tricode}) — {r.games_played} games"
        for r in options.itertuples()
    }
    person_id = st.sidebar.selectbox(
        "Player", options=list(labels), format_func=lambda pid: labels[pid]
    )
    player_name = options.loc[options.person_id == person_id, "player_name"].iloc[0]

    tl = run_query("60_player_timeline", (("person_id", int(person_id)),))
    games = run_query("70_player_games", (("person_id", int(person_id)),))

    if tl.empty:
        st.warning("No data for this player.")
        return

    computed = tl[tl.acwr.notna()]
    played = games[games.minutes_played > 0]

    k1, k2, k3, k4, k5 = st.columns(5)
    if computed.empty:
        k1.metric("Current ACWR", "—", "28-day window not filled", delta_color="off")
    else:
        last = computed.iloc[-1]
        k1.metric(
            "Current ACWR",
            f"{last.acwr:.2f}",
            BAND_LABEL.get(last.acwr_band, ""),
            delta_color="off",
        )
    k2.metric("Last 7 days", f"{tl.iloc[-1].acute_7d:.1f} mi")
    k3.metric("Season total", f"{games.load_miles.sum():.0f} mi")
    k4.metric("Avg speed", f"{played.avg_speed_mph.mean():.2f} mph")
    k5.metric(
        "Games",
        f"{len(played)}",
        f"{int(games.is_back_to_back.fillna(False).sum())} B2B",
        delta_color="off",
    )

    st.plotly_chart(load_chart(tl, player_name), use_container_width=True)
    st.plotly_chart(acwr_chart(tl), use_container_width=True)
    st.plotly_chart(games_chart(games), use_container_width=True)

    st.subheader("Game log")
    table = games.sort_values("game_date", ascending=False).copy()
    table["is_back_to_back"] = table["is_back_to_back"].fillna(False).astype(bool)
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "game_date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
            "matchup": st.column_config.TextColumn("Matchup"),
            "season_type": st.column_config.TextColumn("Type"),
            "minutes_played": st.column_config.NumberColumn("Minutes", format="%.1f"),
            "load_miles": st.column_config.NumberColumn("Distance (mi)", format="%.2f"),
            "avg_speed_mph": st.column_config.NumberColumn("Speed (mph)", format="%.2f"),
            "rest_days": st.column_config.NumberColumn("Rest (days)"),
            "is_back_to_back": st.column_config.CheckboxColumn("B2B"),
        },
    )


def league_tab(meta: pd.Series) -> None:
    st.subheader("Players with the sharpest workload spike on a given date")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    as_of = c1.date_input(
        "Date",
        value=meta.last_game,
        min_value=meta.first_game,
        max_value=meta.last_game,
    )
    min_games = c2.number_input("Min games in season", min_value=1, max_value=82, value=20)
    min_chronic = c3.number_input(
        "Min games in last 28 days",
        min_value=1,
        max_value=15,
        value=8,
        help=(
            "How full the chronic window has to be. A typical NBA month is 14-15 "
            "games, so 8 asks for roughly half a normal month of baseline. Below "
            "about 6 the table fills with ratios pinned to the ceiling of 4.0 — "
            "players whose entire 28-day history sits inside the 7-day window. "
            "That is an absent baseline, not a spike in workload."
        ),
    )
    row_limit = c4.number_input("Rows", min_value=5, max_value=100, value=25)

    risk = run_query(
        "50_league_risk",
        (
            ("as_of", as_of),
            ("min_games", int(min_games)),
            ("min_chronic_games", int(min_chronic)),
            ("row_limit", int(row_limit)),
        ),
    )

    if risk.empty:
        st.info(
            "No ACWR computed for this date. ACWR is not produced during the first 28 "
            "days of a player's season, and no games may have been played that day."
        )
        return

    spread = risk.acwr_band.value_counts()
    cols = st.columns(4)
    for i, band in enumerate(["high", "caution", "normal", "low"]):
        cols[i].metric(BAND_LABEL[band], int(spread.get(band, 0)))

    st.dataframe(
        risk[
            [
                "player_name",
                "team_tricode",
                "acwr",
                "acwr_band",
                "acute_7d",
                "chronic_28d",
                "games_7d",
                "games_28d",
                "games_played",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "player_name": st.column_config.TextColumn("Player"),
            "team_tricode": st.column_config.TextColumn("Team"),
            "acwr": st.column_config.NumberColumn("ACWR", format="%.2f"),
            "acwr_band": st.column_config.TextColumn("Band"),
            "acute_7d": st.column_config.NumberColumn("Acute 7d (mi)", format="%.1f"),
            "chronic_28d": st.column_config.NumberColumn(
                "Chronic 28d (mi/week)", format="%.1f"
            ),
            "games_7d": st.column_config.NumberColumn("Games 7d"),
            "games_28d": st.column_config.NumberColumn("Games 28d"),
            "games_played": st.column_config.NumberColumn("Season games"),
        },
    )

    st.caption(
        "A high ACWR is not an injury prediction. It says that workload over the past "
        "week has risen sharply against the player's own trailing month."
    )


def method_tab(meta: pd.Series) -> None:
    st.markdown(
        f"""
### What is being measured

**Load = distance covered in a game, in miles.** It comes from the NBA's public
player tracking feed. Average speed travels alongside as a separate intensity signal
rather than being folded into load: without high-speed running distance, multiplying
volume by mean speed would invent a "load score" that cannot be defended.

### How ACWR is computed

| | |
|---|---|
| Acute load | total distance over the last **7 days** |
| Chronic load | total distance over the last **28 days** ÷ 4 (a weekly average) |
| ACWR | acute ÷ chronic |

The series is kept **daily**, and a day without a game carries load **0** — the row is
not skipped. That is what lets rest genuinely pull chronic load down, so the spike on
return actually shows up. If only game days were listed, four games in four days and
four games in twenty days would look identical.

The calendar starts at each player's **own first game**, not at the start of the
season. Back-filling zeros for someone who joined the league in February would depress
their chronic load and inflate their ACWR for no physical reason.

**No ACWR is produced during the first 28 days.** Dividing by a half-filled chronic
window hands every player a fake 2-3 in their opening weeks.

**ACWR has a mathematical ceiling of 4.0** — the acute window is a subset of the
chronic one, which is divided by four. A player with a single game in the last 28 days,
falling inside the last 7, lands on exactly 4.0. That reflects an absent baseline, not a
spike in workload. The **"min games in last 28 days"** filter on the league tab exists
precisely to cut that noise; without it the table fills up with players returning from
absence.

### Interpretation bands

| Range | Reading |
|---|---|
| < 0.80 | Undertraining |
| 0.80 – 1.30 | The "sweet spot" |
| 1.30 – 1.50 | Caution |
| > 1.50 | Sharp workload spike — associated with elevated injury risk |

### Limitations

- The public feed gives **total** distance and **mean** speed per game. There is no
  acceleration, no change of direction, no high-speed running distance — largely the
  things that make real load models meaningful.
- **Training load is entirely absent.** These are games only, a fraction of an
  athlete's true total workload.
- ACWR is a monitoring tool, not an injury prediction.

### Data

2025-26 season · **{int(meta.games):,} games** · {int(meta.players):,} players ·
{int(meta.rows_total):,} player-game rows · {int(meta.total_miles):,} miles total ·
{meta.first_game:%d %b %Y} – {meta.last_game:%d %b %Y}
"""
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🏀 NBA Physical Load Monitor")
    st.caption(
        "Athlete workload and ACWR from per-game distance covered — 2025-26 season"
    )

    if not data_available():
        st.error(
            "No data found. Run the ingest first:\n\n"
            "```\npython -m src.ingest --season 2025-26\n```"
        )
        st.stop()

    meta = run_query("80_dataset_meta").iloc[0]

    tab1, tab2, tab3 = st.tabs(["Player", "League", "Method"])
    with tab1:
        player_tab()
    with tab2:
        league_tab(meta)
    with tab3:
        method_tab(meta)


if __name__ == "__main__":
    main()
