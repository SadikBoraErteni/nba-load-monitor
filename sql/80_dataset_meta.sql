-- Dataset bounds: default dates and headline counts for the UI.

SELECT
    MIN(game_date)            AS first_game,
    MAX(game_date)            AS last_game,
    COUNT(DISTINCT game_id)   AS games,
    COUNT(DISTINCT person_id) AS players,
    COUNT(*)                  AS rows_total,
    ROUND(SUM(load_miles), 0) AS total_miles
FROM player_game_load;
