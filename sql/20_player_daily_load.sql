-- Player x DAY: a gap-free daily load series. This is what ACWR rests on.
--
-- Two design decisions live here:
--
-- 1) A day without a game carries load = 0. It is not a missing row. Rest has to
--    actually pull chronic load down, otherwise the spike on return never shows
--    up in the ratio. If we simply listed game days back to back, four games in
--    four days and four games in twenty days would look identical.
--
-- 2) The calendar runs from each player's FIRST game to their LAST game, not
--    across the whole season. Back-filling zeros to opening night for someone
--    who joined the league in February would depress their chronic load and
--    inflate their ACWR for no physical reason.

CREATE OR REPLACE VIEW player_daily_load AS
WITH span AS (
    SELECT
        person_id,
        MIN(game_date) AS first_game_date,
        MAX(game_date) AS last_game_date
    FROM player_game_load
    GROUP BY person_id
),
calendar AS (
    SELECT
        person_id,
        UNNEST(generate_series(first_game_date, last_game_date, INTERVAL 1 DAY))::DATE
            AS load_date
    FROM span
),
game_days AS (
    SELECT
        person_id,
        game_date,
        SUM(load_miles)     AS load_miles,
        SUM(minutes_played) AS minutes_played,
        -- Only games actually played. The tracking feed returns rows for players
        -- who were on the roster but did not appear; counting those would make
        -- the chronic window look well populated when it carries no load at all,
        -- which is exactly the case the league table needs to filter out.
        COUNT(*) FILTER (WHERE minutes_played > 0) AS games_played
    FROM player_game_load
    GROUP BY person_id, game_date
)
SELECT
    c.person_id,
    c.load_date,
    COALESCE(gd.load_miles, 0.0)     AS load_miles,
    COALESCE(gd.minutes_played, 0.0) AS minutes_played,
    COALESCE(gd.games_played, 0)     AS games_played
FROM calendar AS c
LEFT JOIN game_days AS gd
  ON gd.person_id = c.person_id
 AND gd.game_date = c.load_date;
