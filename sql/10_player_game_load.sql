-- Player x game: the physical load one athlete absorbed in a single game.
--
-- Load = distance covered, in miles. Average speed is deliberately NOT folded
-- into the load figure; it travels alongside as a separate intensity signal.
-- The public tracking feed gives total distance and mean speed only — no
-- high-speed running distance — so multiplying volume by speed would invent a
-- "load score" that cannot be defended.
--
-- games_raw holds one row per team per game, so the join needs both keys: we
-- attach each player to their own team's row for that game.

CREATE OR REPLACE VIEW player_game_load AS
SELECT
    t.person_id,
    t.player_name,
    t.team_tricode,
    t.game_id,
    g.game_date,
    g.season_type,
    g.matchup,
    t.minutes_played,
    t.distance_miles AS load_miles,
    t.avg_speed_mph
FROM player_track_raw AS t
JOIN games_raw AS g
  ON g.game_id = t.game_id
 AND g.team_tricode = t.team_tricode;
