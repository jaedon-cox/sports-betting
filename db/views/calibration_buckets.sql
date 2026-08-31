-- calibration_buckets (§3.3, §4.5): a PHYSICAL TABLE, not a matview — a
-- REFRESH would recompute all history under any new bucketing method,
-- silently changing past numbers. Instead the nightly job does an
-- explicit INSERT/UPSERT ON CONFLICT (rollup_date, sport, market,
-- predicted_bucket, method_version), so a dashboard pinned to an old
-- method_version stays numerically stable. v1: blended-only, 10 deciles
-- via width_bucket(); per-market split is a non-breaking future add
-- (already representable in this schema without a migration).
--
-- market uses the same non-NULL 'blended' sentinel as record_summary
-- (see that file's comment) — ON CONFLICT needs a real value to match
-- against, since Postgres never treats two NULLs as conflicting.
--
-- Population is the nightly settlement job's responsibility (Job F,
-- pipeline/wave 2) — this migration only defines the shape.

CREATE TABLE calibration_buckets (
    rollup_date         DATE NOT NULL,
    sport               TEXT NOT NULL DEFAULT 'mlb',
    market              TEXT NOT NULL DEFAULT 'blended',
    predicted_bucket    SMALLINT NOT NULL CHECK (predicted_bucket BETWEEN 1 AND 10),
    method_version      TEXT NOT NULL,
    n                   INTEGER NOT NULL CHECK (n >= 0),  -- exposed per "every aggregate shows its N"
    avg_predicted_prob  NUMERIC(6, 5) CHECK (avg_predicted_prob IS NULL OR avg_predicted_prob BETWEEN 0 AND 1),
    actual_win_rate     NUMERIC(6, 5) CHECK (actual_win_rate IS NULL OR actual_win_rate BETWEEN 0 AND 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (rollup_date, sport, market, predicted_bucket, method_version)
);

-- Mutable by design (explicit UPSERT, not append-only) — no
-- fn_reject_mutation guard here, unlike every other table in this
-- schema. fn_touch_updated_at and fn_reject_mutation both come from
-- db/migrations/001_reference_and_versioning.sql.
CREATE TRIGGER trg_calibration_buckets_touch_updated_at
    BEFORE UPDATE ON calibration_buckets
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();
