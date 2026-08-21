-- Player dimension: drives the selector and the filters in the UI.
--
-- games_played counts only games actually played. The tracking endpoint also
-- returns rows for players who were on the roster but did not appear (DNP);
-- counting those as games would distort per-game averages and would quietly
-- weaken the minimum-games filter that keeps noise out of the league table.

CREATE OR REPLACE VIEW players AS
SELECT
    person_id,
    MAX(player_name)                                      AS player_name,
    ARG_MAX(team_tricode, game_date)                      AS team_tricode,
    COUNT(*) FILTER (WHERE minutes_played > 0)            AS games_played,
    SUM(load_miles)                                       AS total_miles,
    AVG(minutes_played) FILTER (WHERE minutes_played > 0) AS avg_minutes,
    AVG(avg_speed_mph)  FILTER (WHERE minutes_played > 0) AS avg_speed_mph,
    MIN(game_date)                                        AS first_game_date,
    MAX(game_date)                                        AS last_game_date
FROM player_game_load
GROUP BY person_id;
