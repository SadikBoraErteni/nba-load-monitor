-- Daily load and ACWR series for one player; the data behind the charts.
-- Parameter: $person_id (BIGINT)

SELECT
    load_date,
    load_miles,
    minutes_played,
    games_played,
    day_index,
    games_7d,
    games_28d,
    acute_7d,
    chronic_28d,
    acwr,
    acwr_band
FROM player_acwr
WHERE person_id = $person_id
ORDER BY load_date;
