-- Enable RLS on every table. Run order: db/migrations/ -> db/views/ ->
-- db/policies/ (policies below grant on record_summary / mv_clv_trend /
-- mv_roi_curve / calibration_buckets, which live in db/views/).
--
-- Postgres RLS is default-deny: enabling it with zero policies already
-- satisfies the Critic's "explicit anon-deny" must-fix (§3.5, §6 finding
-- #1) for any table that gets no policy at all below (raw_snapshots).
-- Every policy this team writes is scoped `TO authenticated` — never
-- `TO public`/`anon` — so a logged-out visitor, even holding a leaked
-- anon key, sees nothing.
--
-- Belt-and-suspenders: RLS blocks row access independent of GRANTs, but
-- a blanket REVOKE first means the anon-deny posture holds even if
-- Supabase's project bootstrapping ever grants anon/PUBLIC default
-- privileges on this schema. "ALL TABLES" here also covers views,
-- matviews and foreign tables per Postgres's REVOKE docs, so this one
-- statement locks down record_summary/mv_clv_trend/mv_roi_curve too.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon;

ALTER TABLE model_versions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE markets              ENABLE ROW LEVEL SECURITY;
ALTER TABLE sport_markets        ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams                ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_runs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE games                ENABLE ROW LEVEL SECURITY;
ALTER TABLE results              ENABLE ROW LEVEL SECURITY;
ALTER TABLE picks                ENABLE ROW LEVEL SECURITY;
ALTER TABLE line_snapshots       ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineup_snapshots     ENABLE ROW LEVEL SECURITY;
ALTER TABLE injury_snapshots     ENABLE ROW LEVEL SECURITY;
ALTER TABLE weather_snapshots    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pick_settlements     ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibration_buckets  ENABLE ROW LEVEL SECURITY;

-- raw_snapshots / odds_budget_usage: RLS enabled, deliberately NO policy
-- anywhere in this directory. Both are internal pipeline-ops data, not a
-- frontend read surface (§4.5 doesn't list either) — this locks them
-- from PostgREST for every role, authenticated included. Only the
-- service-role key (which bypasses RLS entirely) and the
-- fn_odds_budget_month_total RPC (called with that same key) can reach
-- them.
ALTER TABLE raw_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE odds_budget_usage ENABLE ROW LEVEL SECURITY;

-- Matviews (record_summary, mv_clv_trend, mv_roi_curve): Postgres does
-- NOT support ROW LEVEL SECURITY / CREATE POLICY on materialized views
-- at all (RLS is a table-only feature) — there is no ALTER MATERIALIZED
-- VIEW ... ENABLE ROW LEVEL SECURITY. Access control for these three is
-- GRANT-only: the REVOKE ALL above already locks out anon/PUBLIC, and
-- 002_authenticated_read_grants.sql explicitly GRANTs SELECT to
-- authenticated. That's sufficient here since none of them need
-- per-row filtering (every authenticated user sees the whole rollup) —
-- the thing RLS policies would normally add.

ALTER TABLE profiles          ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_saved_picks  ENABLE ROW LEVEL SECURITY;
