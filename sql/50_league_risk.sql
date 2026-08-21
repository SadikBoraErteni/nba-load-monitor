-- "Who to watch today": players with the highest ACWR on a given date.
-- Parameters: $as_of (DATE), $min_games (INT), $min_chronic_games (INT), $row_limit (INT)
--
-- Two separate filters, because there are two separate sources of noise:
--
--   min_games          drops players with a thin season. An ACWR can be computed
--                      after three games; it does not mean anything physically.
--
--   min_chronic_games  drops thin CHRONIC WINDOWS. A player with one game in the
--                      last 28 days is pinned to the ceiling of 4.0 by
--                      construction: the acute window is a subset of the chronic
--                      one, and the chronic sum is divided by four. That is an
--                      absent baseline, not a spike. Without this filter the
--                      table fills up with players returning from absence.

SELECT
    p.player_name,
    p.team_tricode,
    a.person_id,
    a.load_date,
    a.acwr,
    a.acwr_band,
    a.acute_7d,
    a.chronic_28d,
    a.games_7d,
    a.games_28d,
    p.games_played
FROM player_acwr AS a
JOIN players AS p USING (person_id)
WHERE a.load_date = $as_of
  AND a.acwr IS NOT NULL
  AND p.games_played >= $min_games
  AND a.games_28d >= $min_chronic_games
ORDER BY a.acwr DESC
LIMIT $row_limit;
