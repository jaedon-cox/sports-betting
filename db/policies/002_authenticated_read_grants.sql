-- Authenticated-read surface (§3.5, §5): every logged-in user can read
-- every fact/reference/rollup table — there is no per-user row filter on
-- picks/games/results/etc, only on the user-owned tables in
-- 003_user_owned_rls.sql. GRANT is separate from RLS: RLS restricts which
-- rows are visible, GRANT restricts whether the role may query the
-- relation at all — Supabase needs both for a custom-migrated table.
--
-- Note on views vs matviews: v_todays_picks / v_pick_archive /
-- v_pick_clv_live are plain views created WITH (security_invoker = true)
-- in db/views/, so RLS on their underlying base tables (picks, games,
-- teams, line_snapshots, pick_settlements) is what actually gates them —
-- they get a GRANT here but no CREATE POLICY of their own. record_summary
-- / mv_clv_trend / mv_roi_curve are materialized views, and Postgres does
-- not support RLS/CREATE POLICY on matviews at all (table-only feature)
-- — access control for those three is GRANT-only, backed by the blanket
-- REVOKE ALL ... FROM PUBLIC, anon in 001_enable_rls.sql.

GRANT USAGE ON SCHEMA public TO authenticated;

CREATE POLICY authenticated_read ON model_versions     FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON markets              FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON sport_markets        FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON teams                FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON model_runs           FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON games                FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON results              FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON picks                FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON line_snapshots       FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON lineup_snapshots     FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON injury_snapshots     FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON weather_snapshots    FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON pick_settlements     FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON pipeline_runs        FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_read ON calibration_buckets  FOR SELECT TO authenticated USING (true);

GRANT SELECT ON
    model_versions, markets, sport_markets, teams, model_runs, games, results, picks,
    line_snapshots, lineup_snapshots, injury_snapshots, weather_snapshots, pick_settlements,
    pipeline_runs, calibration_buckets, record_summary, mv_clv_trend, mv_roi_curve,
    v_todays_picks, v_pick_archive, v_pick_clv_live
    TO authenticated;
