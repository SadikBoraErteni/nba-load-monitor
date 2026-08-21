-- ACWR — Acute:Chronic Workload Ratio. The headline metric of this project.
--
--   acute   = total distance over the last 7 days
--   chronic = total distance over the last 28 days / 4   (reduces it to a weekly average)
--   acwr    = acute / chronic
--
-- Because 20_player_daily_load produces a gap-free daily series, ROWS and RANGE
-- are equivalent here: counting rows is counting days. ROWS is the cheaper of
-- the two.
--
-- WARM-UP WINDOW: ACWR stays NULL until a player has 28 days of history. Dividing
-- by a half-filled chronic window hands every player a fake 2-3 in their opening
-- weeks — the quiet, classic way to make this kind of dashboard unreadable.
--
-- Interpretation bands, as commonly used in the sports science literature:
--   < 0.80      undertraining / detraining zone
--   0.80-1.30   the "sweet spot"
--   1.30-1.50   caution
--   > 1.50      sharp spike in workload, associated with elevated injury risk

CREATE OR REPLACE VIEW player_acwr AS
WITH windowed AS (
    SELECT
        person_id,
        load_date,
        load_miles,
        minutes_played,
        games_played,
        ROW_NUMBER() OVER w AS day_index,
        SUM(load_miles) OVER (
            PARTITION BY person_id ORDER BY load_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS acute_7d,
        SUM(load_miles) OVER (
            PARTITION BY person_id ORDER BY load_date
            ROWS BETWEEN 27 PRECEDING AND CURRENT ROW
        ) / 4.0 AS chronic_28d_raw,
        -- How full each window actually is. This matters as much as the ratio:
        -- with a single game in the chronic window the ratio is pinned to its
        -- mathematical ceiling of 4.0, which reflects missing baseline rather
        -- than a genuine spike in workload.
        SUM(games_played) OVER (
            PARTITION BY person_id ORDER BY load_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS games_7d,
        SUM(games_played) OVER (
            PARTITION BY person_id ORDER BY load_date
            ROWS BETWEEN 27 PRECEDING AND CURRENT ROW
        ) AS games_28d
    FROM player_daily_load
    WINDOW w AS (PARTITION BY person_id ORDER BY load_date)
)
SELECT
    person_id,
    load_date,
    load_miles,
    minutes_played,
    games_played,
    day_index,
    games_7d,
    games_28d,
    acute_7d,
    CASE WHEN day_index >= 28 THEN chronic_28d_raw END AS chronic_28d,
    CASE
        WHEN day_index >= 28 AND chronic_28d_raw > 0
        THEN acute_7d / chronic_28d_raw
    END AS acwr,
    CASE
        WHEN day_index < 28 OR chronic_28d_raw = 0 THEN NULL
        WHEN acute_7d / chronic_28d_raw > 1.50 THEN 'high'
        WHEN acute_7d / chronic_28d_raw > 1.30 THEN 'caution'
        WHEN acute_7d / chronic_28d_raw < 0.80 THEN 'low'
        ELSE 'normal'
    END AS acwr_band
FROM windowed;
