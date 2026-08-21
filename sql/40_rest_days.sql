-- Schedule context: how much rest preceded each game, and which are back-to-backs.
--
--   rest_days = number of empty days between two games
--   Jan 1 + Jan 2  -> rest_days = 0  -> back-to-back
--   Jan 1 + Jan 3  -> rest_days = 1
--
-- The first game of a player's season has no predecessor, so rest_days is NULL
-- rather than 0: "rested zero days" would be a claim we cannot make.

CREATE OR REPLACE VIEW player_game_rest AS
SELECT
    person_id,
    player_name,
    team_tricode,
    game_id,
    game_date,
    season_type,
    matchup,
    minutes_played,
    load_miles,
    avg_speed_mph,
    LAG(game_date) OVER w AS prev_game_date,
    DATE_DIFF('day', LAG(game_date) OVER w, game_date) - 1 AS rest_days,
    DATE_DIFF('day', LAG(game_date) OVER w, game_date) = 1 AS is_back_to_back
FROM player_game_load
WINDOW w AS (PARTITION BY person_id ORDER BY game_date);
