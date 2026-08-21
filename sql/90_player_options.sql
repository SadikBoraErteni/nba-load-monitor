-- Player picker for the UI, heaviest workloads first.
-- Parameter: $min_games (INT)

SELECT
    person_id,
    player_name,
    team_tricode,
    games_played,
    ROUND(total_miles, 1) AS total_miles
FROM players
WHERE games_played >= $min_games
ORDER BY total_miles DESC;
