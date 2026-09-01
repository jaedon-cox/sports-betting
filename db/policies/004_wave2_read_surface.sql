-- Read surface for the relations added after wave 1: slate_status
-- (009) and record_breakdown (db/views/). Same posture as 001/002 —
-- authenticated-only, explicit anon-deny (§3.5).
--
-- Kept as a new file rather than edits to 001/002 so those stay exactly
-- as applied. Re-asserting REVOKE here (rather than relying on 001's
-- blanket REVOKE ALL ON ALL TABLES) makes this file correct on its own
-- against an already-migrated database, where 001 does not re-run.

REVOKE ALL ON slate_status, record_breakdown FROM PUBLIC, anon;

ALTER TABLE slate_status ENABLE ROW LEVEL SECURITY;

-- DROP IF EXISTS so this whole file is re-runnable. That matters because
-- db/APPLY_ORDER.md requires re-running it after ANY later DDL — a
-- function that is dropped and recreated silently regains the EXECUTE
-- grant this file revokes, and the pgrst NOTIFY at the bottom has to
-- fire again for the new relation to be routable at all. Every other
-- statement here is already idempotent; bare CREATE POLICY was the only
-- one that would abort the re-run partway, leaving the revokes and the
-- NOTIFY below it unapplied. Policies 001-003 are NOT re-runnable for
-- exactly that reason, which is why the re-run rule names this file
-- alone.
DROP POLICY IF EXISTS authenticated_read ON slate_status;
CREATE POLICY authenticated_read ON slate_status
    FOR SELECT TO authenticated USING (true);

-- slate_status is read directly — one row per (sport, slate_date), so
-- there is nothing for a view to resolve. record_breakdown is a matview:
-- Postgres supports no RLS on matviews, so GRANT is the only control,
-- exactly as for record_summary / mv_clv_trend / mv_roi_curve (see 001's
-- closing note).
GRANT SELECT ON slate_status, record_breakdown TO authenticated;

-- ---------------------------------------------------------------------
-- Function exposure. Postgres grants EXECUTE on every new function to
-- PUBLIC by default, and PostgREST publishes every function in the
-- exposed schema at /rpc/<name>. anon is a member of PUBLIC and the anon
-- key is not secret, so every RPC below is reachable by an anonymous
-- caller as shipped.
--
-- None is currently exploitable — each runs as the caller, who has no
-- INSERT grant and is blocked by RLS besides — but each depends on a
-- second control holding, and closing them costs nothing. Writes are
-- service-role only (§5), and every function here is a pipeline call.
REVOKE ALL ON FUNCTION fn_publish_run(BIGINT, TEXT, DATE, TEXT, TEXT, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_publish_run(BIGINT, TEXT, DATE, TEXT, TEXT, JSONB)
    TO service_role;

REVOKE ALL ON FUNCTION fn_odds_budget_month_total(TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_odds_budget_month_total(TEXT) TO service_role;

-- Same treatment for the two pipeline read RPCs (012). `authenticated`
-- could reconstruct both from the tables it can already SELECT, so this
-- is not about secrecy — it is about the /rpc surface staying exactly
-- the set of calls someone meant to publish.
REVOKE ALL ON FUNCTION fn_latest_lines(TEXT, DATE, TIMESTAMPTZ, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_latest_lines(TEXT, DATE, TIMESTAMPTZ, TEXT) TO service_role;

REVOKE ALL ON FUNCTION fn_unsettled_picks(TEXT, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_unsettled_picks(TEXT, TIMESTAMPTZ) TO service_role;

REVOKE ALL ON FUNCTION fn_settled_picks_for_date(TEXT, DATE) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_settled_picks_for_date(TEXT, DATE) TO service_role;

-- fn_record_results WRITES. Leaving EXECUTE on PUBLIC here would put an
-- insert path to final scores behind the non-secret anon key — RLS would
-- still refuse it (anon has no INSERT grant on results), but this is the
-- one function in the schema where the second control failing would
-- corrupt the track record rather than leak a read.
REVOKE ALL ON FUNCTION fn_record_results(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_record_results(JSONB) TO service_role;

REVOKE ALL ON FUNCTION fn_backtest_rows(TEXT, DATE, DATE, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_backtest_rows(TEXT, DATE, DATE, TEXT) TO service_role;

-- DELIBERATELY NOT REVOKED, do not "finish the job" here:
--   * The trigger functions (fn_reject_mutation, fn_touch_updated_at,
--     fn_guard_model_runs_update, fn_validate_pick,
--     fn_handle_new_auth_user). Firing a trigger checks EXECUTE against
--     the role performing the INSERT, so revoking from PUBLIC without
--     granting every writing role back would break every write in the
--     schema. They are also unreachable over /rpc — PostgREST does not
--     publish functions returning `trigger`.
--   * The pure scalar helpers (fn_american_payout_multiplier,
--     fn_side_role, fn_edge_bucket, fn_bucket_rank). They read no
--     relation and return a constant function of their argument, so
--     calling one discloses nothing.
--   * fn_refresh_rollups, which locks its own grants down at its
--     definition site (011_rollup_refresh.sql) because SECURITY DEFINER
--     makes that part of the function's own safety story.

-- ---------------------------------------------------------------------
-- PostgREST schema cache.
--
-- This is the missing half of "are the matviews reachable by
-- authenticated": GRANT decides whether a role MAY read a relation,
-- but PostgREST only routes to relations in its in-memory schema cache,
-- which it builds at startup and rebuilds only on this NOTIFY. Applying
-- these files as raw SQL — which is how this repo is meant to be applied
-- — does not trigger a rebuild, so a newly created relation answers
-- 404 PGRST205 ("Could not find the table 'public.x' in the schema
-- cache") to a perfectly authorised request. That failure looks exactly
-- like a missing GRANT and is the likeliest reason a matview appears
-- unreachable.
--
-- Must be the last statement applied. Re-run it after ANY DDL.
NOTIFY pgrst, 'reload schema';
