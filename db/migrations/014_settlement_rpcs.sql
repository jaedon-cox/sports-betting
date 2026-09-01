-- The two remaining Job F functions `pipeline` calls from
-- src/sbm/jobs/rpc.py. Same reasoning as 012: PostgrestClient exposes no
-- filtered select, so each read the pipeline needs is one named function
-- over /rpc rather than a general-purpose query builder.
-- Grants are in db/policies/004_wave2_read_surface.sql.

-- ---------------------------------------------------------------------
-- fn_settled_picks_for_date — every settled pick on one slate date.
--
-- The COMPLETE set for the date, deliberately not a delta.
-- calibration_buckets is upserted per (rollup_date, sport, market,
-- predicted_bucket, method_version), so a rerun that settled only the
-- stragglers must still recompute each bucket from the whole day —
-- otherwise it overwrites a full bucket with a partial one and silently
-- restates published calibration. Complete-set-in, complete-row-out is
-- what makes that upsert idempotent (§3.3).
--
-- No `recommended` filter: calibration, like CLV, is measured over ALL
-- evaluated picks (doc §7). Filtering to recommended would grade the
-- model only where it already believed it had an edge, which is exactly
-- the selection effect the "keep recommended=false rows" design exists
-- to avoid.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_settled_picks_for_date(
    p_sport        TEXT,
    p_rollup_date  DATE
) RETURNS TABLE (
    market      TEXT,
    model_prob  NUMERIC,
    outcome     TEXT
)
LANGUAGE sql STABLE AS $$
    SELECT p.market, p.model_prob, ps.outcome
    FROM picks p
    JOIN pick_settlements ps ON ps.pick_id = p.id
    WHERE p.sport = p_sport
      AND p.game_date = p_rollup_date
    ORDER BY p.market, p.id;
$$;

-- ---------------------------------------------------------------------
-- fn_record_results — insert final scores, skipping games already
-- recorded; returns the number of rows actually added.
--
-- Neither client verb works for this table, which is why it needs a
-- function (`pipeline`'s finding, and it is correct):
--   * `insert` raises a unique violation on a rerun, so one already-
--     recorded game fails the whole nightly batch.
--   * `upsert` is worse: PostgREST's merge-duplicates issues ON CONFLICT
--     DO UPDATE, and results carries a reject-mutation trigger (§3.1),
--     so the UPDATE raises — and if it ever did not, it would silently
--     overwrite a final score, which is the exact thing insert-once
--     exists to prevent.
-- ON CONFLICT DO NOTHING fires no UPDATE, so no trigger runs and the
-- append-only guarantee is untouched. A game already recorded stays as
-- recorded; a correction is a human decision, not a nightly rerun.
--
-- src/sbm/store/facts.py::write_results keeps the strict plain-INSERT
-- path deliberately — a caller that believes it is writing a brand-new
-- score should still hear about it if the row exists. This function is
-- for the nightly sweep, where re-seeing a settled game is normal.
--
-- p_results is an array of objects matching store.facts.ResultRow:
-- {game_id, home_score, away_score, final_status, detail?}.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_record_results(p_results JSONB) RETURNS INTEGER
LANGUAGE sql VOLATILE AS $$
    WITH ins AS (
        INSERT INTO results (game_id, home_score, away_score, final_status, detail)
        SELECT
            (r ->> 'game_id')::BIGINT,
            (r ->> 'home_score')::INTEGER,
            (r ->> 'away_score')::INTEGER,
            r ->> 'final_status',
            NULLIF(r -> 'detail', 'null'::JSONB)
        FROM jsonb_array_elements(p_results) AS r
        ON CONFLICT (game_id) DO NOTHING
        RETURNING 1
    )
    SELECT COUNT(*)::INTEGER FROM ins;
$$;
