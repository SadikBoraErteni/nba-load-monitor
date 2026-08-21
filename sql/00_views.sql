-- Base views over the Parquet layer.
--
-- Every query downstream reads only player_track_raw and games_raw, and never
-- needs to know whether the data sits on local disk or in object storage. The
-- test suite feeds synthetic tables under these same two names, so the SQL that
-- is tested is literally the SQL that ships.
--
-- {player_track} and {games} are filled in by src/db.py.

CREATE OR REPLACE VIEW player_track_raw AS
SELECT * FROM read_parquet('{player_track}');

CREATE OR REPLACE VIEW games_raw AS
SELECT * FROM read_parquet('{games}');
