-- fn_refresh_rollups(): the one call Job F makes to rebuild every
-- rollup matview (§3.3, §2.4 job F "refresh all rollup matviews").
--
-- WHY THIS EXISTS AT ALL: src/sbm/store/ talks to Postgres only over
-- PostgREST, which has no SQL endpoint — a job cannot issue REFRESH
-- MATERIALIZED VIEW from Python. A function called over /rpc is the only
-- path, exactly as fn_publish_run is for the publish transaction.
--
-- WHY NOT CONCURRENTLY, despite §3.3 asking for it: `REFRESH
-- MATERIALIZED VIEW CONCURRENTLY` is one of the statements Postgres
-- refuses to run inside a transaction block, and a plpgsql body always
-- is one — it fails with "cannot be executed from a function". There is
-- no arrangement of PL/pgSQL that gets around this. So these are plain
-- refreshes, which take ACCESS EXCLUSIVE on each matview for the length
-- of the call. That is the right trade here: the rollups are a few
-- thousand rows over ~32k picks/yr (§3.4), this runs once nightly
-- post-slate, and readers are a handful of authenticated users. The
-- unique indexes in db/views/ are kept regardless — they enforce the
-- grain, serve lookups, and leave CONCURRENTLY available to a human in
-- psql, where it is not inside a function.
--
-- One transaction covers all four, so a reader never catches
-- record_summary rebuilt while mv_clv_trend still holds yesterday's
-- running totals. If any refresh fails the whole set rolls back to the
-- previous night's numbers rather than landing half-updated.
--
-- SECURITY DEFINER because REFRESH requires ownership of the matview and
-- `service_role` (the key the pipeline holds) does not own them — the
-- role that ran db/views/ does. This assumes that role also owns this
-- function, which holds when the two directories are applied by the same
-- role, as the documented run order does. SET search_path is the
-- standard guard against a caller-controlled search_path, matching
-- fn_handle_new_auth_user() in 006_users_and_auth.sql.
--
-- Note for whoever adds the next matview: add it here too, or it will
-- silently serve stale numbers forever with nothing failing.
--
-- This migration names matviews that db/views/ has not created yet at
-- migration time, and that is fine: PL/pgSQL defers name resolution of
-- embedded statements to first execution, so CREATE FUNCTION succeeds
-- against relations that do not exist. (A LANGUAGE sql function would
-- NOT — it resolves at creation. Do not "simplify" this to LANGUAGE sql.)

CREATE OR REPLACE FUNCTION fn_refresh_rollups() RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    -- record_summary first: mv_clv_trend and mv_roi_curve are windows
    -- over it, so refreshing them against a stale base would publish a
    -- cumulative curve that disagrees with its own daily rows.
    REFRESH MATERIALIZED VIEW record_summary;
    REFRESH MATERIALIZED VIEW mv_clv_trend;
    REFRESH MATERIALIZED VIEW mv_roi_curve;
    -- Reads picks/pick_settlements directly, so order-independent — kept
    -- last only so a failure here cannot leave the three the Record page
    -- depends on most unrefreshed.
    REFRESH MATERIALIZED VIEW record_breakdown;
END;
$$;

-- Postgres grants EXECUTE on a new function to PUBLIC by default, and
-- PostgREST exposes every function in the exposed schema at /rpc/<name>.
-- Without this REVOKE, a holder of the (non-secret) anon key could POST
-- /rest/v1/rpc/fn_refresh_rollups and force an exclusive lock on every
-- rollup at will — and SECURITY DEFINER means it would succeed. Only the
-- pipeline's service-role key may call this.
REVOKE ALL ON FUNCTION fn_refresh_rollups() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_refresh_rollups() TO service_role;
