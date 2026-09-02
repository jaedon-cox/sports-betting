-- Grants for 017's two fact tables and 018's three read functions.
--
-- Split from policies/004 rather than appended to it because 004 ends
-- with `NOTIFY pgrst, 'reload schema'` and APPLY_ORDER.md documents that
-- file as the thing to re-run after ANY later DDL. Editing it would make
-- "re-run 004" and "apply the new migration" the same action, which is
-- exactly the ambiguity that file exists to remove.

-- Service-role only. Nothing here is reader-facing: these are model
-- inputs, and exposing them to `authenticated` would publish the
-- feature set the edge is built on (§5). policies/001's blanket
-- REVOKE already locked out anon and PUBLIC; these tables were created
-- after it ran, so they need their own.
REVOKE ALL ON pitcher_game_stats, team_batting_game_stats FROM PUBLIC, anon, authenticated;

ALTER TABLE pitcher_game_stats       ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_batting_game_stats  ENABLE ROW LEVEL SECURITY;
-- No policy is created for either: RLS with zero policies denies every
-- role except the table owner and service_role (which bypasses RLS
-- entirely). That is the intended posture -- deny by default, and the
-- pipeline reaches them with the service key.

GRANT SELECT, INSERT, UPDATE ON pitcher_game_stats      TO service_role;
GRANT SELECT, INSERT, UPDATE ON team_batting_game_stats TO service_role;

-- UPDATE is granted deliberately, unlike every other fact table: the
-- writer upserts with merge-duplicates so Statcast's post-game
-- revisions land (db/migrations/017's header).

REVOKE ALL ON FUNCTION fn_pitcher_game_form(TEXT[], DATE, DATE) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fn_bullpen_game_form(TEXT[], DATE, DATE) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fn_team_batting_form(TEXT[], DATE, DATE) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION fn_pitcher_game_form(TEXT[], DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION fn_bullpen_game_form(TEXT[], DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION fn_team_batting_form(TEXT[], DATE, DATE) TO service_role;

REVOKE ALL ON FUNCTION fn_injury_status_asof(BIGINT[], TIMESTAMPTZ, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fn_weather_asof(BIGINT[], TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION fn_injury_status_asof(BIGINT[], TIMESTAMPTZ, TIMESTAMPTZ) TO service_role;
GRANT EXECUTE ON FUNCTION fn_weather_asof(BIGINT[], TIMESTAMPTZ) TO service_role;

NOTIFY pgrst, 'reload schema';
