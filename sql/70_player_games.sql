-- Game-by-game breakdown for one player, with schedule context attached.
-- Parameter: $person_id (BIGINT)

SELECT
    game_date,
    matchup,
    season_type,
    minutes_played,
    load_miles,
    avg_speed_mph,
    rest_days,
    is_back_to_back
FROM player_game_rest
WHERE person_id = $person_id
ORDER BY game_date;
