-- record_breakdown (§4.1 item 3): the favourite/underdog and edge-bucket
-- splits the Model Record page asks for. record_summary's grain is
-- (rollup_date, sport, market) only, so those breakdowns were not
-- buildable and the page shipped a footnote apologising for it.
--
-- WHY A SECOND MATVIEW instead of widening record_summary's grain:
-- widening it would change the meaning of every existing row (each date/
-- market would fan out into several), break the unique index that
-- mv_clv_trend and mv_roi_curve build their running windows on, and
-- break every frontend read that sums record_summary over the daily
-- grain. This view is purely additive — nothing that exists today reads
-- it, and nothing that exists today changes.
--
-- WHY A LONG SHAPE (dimension, bucket) rather than two more grain
-- columns: two breakdowns with different domains in the same row would
-- force a cross-product (favourite x edge-bucket), which is a different,
-- much sparser question than the two marginals the page actually asks
-- for. `dimension` is data, not an enum in code (CLAUDE.md rule 7) — a
-- third breakdown is one more row in the VALUES list below and a matview
-- rebuild, with no schema change and no frontend type change.
--
-- Columns are deliberately identical to record_summary's, so the
-- frontend's existing "sum over the daily grain" composition
-- (web/src/lib/record.ts) works here unchanged with one extra filter.
--
-- RUN ORDER: after record_summary.sql — this file reuses that file's
-- fn_american_payout_multiplier rather than redefining the payout math a
-- second place it could drift.

-- Favourite/underdog from the DE-VIGGED fair probability of the side the
-- model took, not from the sign of market_odds_american. In a 2-way book
-- the de-vigged probs sum to 1, so `>= 0.5` is exactly "the shorter
-- price" with the vig removed — the same split, minus the artifact where
-- a -110/-110 total makes both sides look like favourites. It also
-- generalises to any market with a fair prob, including future props,
-- which the odds-sign version does not.
--
-- Market odds appear here only in the reporting layer, never as a model
-- input (CLAUDE.md rule 3).
CREATE OR REPLACE FUNCTION fn_side_role(fair_prob NUMERIC) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN fair_prob IS NULL THEN 'unknown'
        WHEN fair_prob >= 0.5  THEN 'favorite'
        ELSE 'underdog'
    END;
$$;

-- Edge buckets over picks.edge_pct (= model_prob - market_fair_prob, in
-- probability points). Boundaries live in exactly one place so they
-- cannot drift between this view and anything that reads it.
--
-- Honest limitation, and the reason for the 'edge_v1' bucket_scheme
-- literal below: this is a MATVIEW, so a REFRESH recomputes all history
-- under whatever boundaries are current — the same hazard that made
-- calibration_buckets a physical table (§3.3). It is a lesser hazard
-- here (a descriptive split, not a published calibration claim), so the
-- cheaper mechanism is used: changing a boundary must also change the
-- scheme label, which makes the restatement visible in the data instead
-- of silent. If this view ever backs a claim someone pins to, promote it
-- to a physical table with an UPSERT the way calibration_buckets did.
CREATE OR REPLACE FUNCTION fn_edge_bucket(edge NUMERIC) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN edge IS NULL   THEN 'unknown'
        WHEN edge <  0      THEN 'negative'
        WHEN edge <  0.01   THEN '0-1%'
        WHEN edge <  0.02   THEN '1-2%'
        WHEN edge <  0.03   THEN '2-3%'
        WHEN edge <  0.05   THEN '3-5%'
        ELSE                     '5%+'
    END;
$$;

-- Display order for the buckets above, PER DIMENSION — ranks are only
-- ever compared within one `dimension`, so 'favorite' and 'negative'
-- sharing rank 1 is correct, not a collision. Carried as a column so the
-- frontend never orders by parsing a label; 'unknown' sorts last.
CREATE OR REPLACE FUNCTION fn_bucket_rank(bucket TEXT) RETURNS SMALLINT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE bucket
        WHEN 'favorite' THEN 1 WHEN 'underdog' THEN 2
        WHEN 'negative' THEN 1 WHEN '0-1%' THEN 2 WHEN '1-2%' THEN 3
        WHEN '2-3%' THEN 4 WHEN '3-5%' THEN 5 WHEN '5%+' THEN 6
        ELSE 99  -- 'unknown'
    END::SMALLINT;
$$;

CREATE MATERIALIZED VIEW record_breakdown AS
WITH base AS (
    SELECT
        p.game_date AS rollup_date,
        p.sport,
        p.market,
        fn_side_role(p.market_fair_prob) AS side_role,
        fn_edge_bucket(p.edge_pct) AS edge_bucket,
        p.recommended, p.kelly_stake_fraction, p.market_odds_american, p.edge_pct,
        ps.outcome, ps.clv_pct
    FROM picks p
    JOIN pick_settlements ps ON ps.pick_id = p.id
),
-- One scan of base, fanned out to one row per (pick, dimension). Adding
-- a third breakdown is one more VALUES row.
labeled AS (
    SELECT b.*, d.dimension, d.bucket
    FROM base b
    CROSS JOIN LATERAL (VALUES
        ('side_role',   b.side_role),
        ('edge_bucket', b.edge_bucket)
    ) AS d(dimension, bucket)
),
agg AS (
    SELECT
        rollup_date,
        sport,
        market AS market_raw,  -- NULL only in the blended grouping set
        dimension,
        bucket,
        COUNT(*) AS n_evaluated,
        COUNT(*) FILTER (WHERE recommended) AS n_recommended,
        COUNT(*) FILTER (WHERE recommended AND outcome = 'win')  AS wins,
        COUNT(*) FILTER (WHERE recommended AND outcome = 'loss') AS losses,
        COUNT(*) FILTER (WHERE recommended AND outcome IN ('push', 'void')) AS pushes,
        COALESCE(SUM(kelly_stake_fraction) FILTER (WHERE recommended), 0) AS units_staked,
        COALESCE(SUM(
            CASE outcome
                WHEN 'win'  THEN kelly_stake_fraction * fn_american_payout_multiplier(market_odds_american)
                WHEN 'loss' THEN -kelly_stake_fraction
                ELSE 0
            END
        ) FILTER (WHERE recommended), 0) AS units_won,
        -- RELATIVE CLV, the units core/clv.py defines and pick_settlements
        -- stores — never the absolute v_pick_clv_live.clv_abs_live.
        AVG(clv_pct) AS avg_clv_pct,
        AVG((clv_pct > 0)::INT::NUMERIC) AS clv_positive_rate,
        AVG(edge_pct) AS avg_edge_pct
    FROM labeled
    GROUP BY GROUPING SETS (
        (rollup_date, sport, market, dimension, bucket),
        (rollup_date, sport, dimension, bucket)
    )
)
SELECT
    rollup_date,
    sport,
    -- Same non-NULL 'blended' sentinel as record_summary: a plain UNIQUE
    -- index can't treat two NULLs as a conflict, and every grain column
    -- must be non-NULL for the unique index to actually identify a row.
    COALESCE(market_raw, 'blended') AS market,
    dimension,
    bucket,
    -- Functionally determined by `dimension`, so not part of the grain.
    -- Bump the label on the same line as any boundary change above.
    CASE dimension
        WHEN 'edge_bucket' THEN 'edge_v1'
        WHEN 'side_role'   THEN 'side_role_v1'
    END AS bucket_scheme,
    fn_bucket_rank(bucket) AS bucket_rank,
    n_evaluated,
    n_recommended,
    wins,
    losses,
    pushes,
    units_staked,
    units_won,
    CASE WHEN units_staked = 0 THEN NULL ELSE units_won / units_staked END AS roi_pct,
    avg_clv_pct,
    clv_positive_rate,
    avg_edge_pct
FROM agg;

CREATE UNIQUE INDEX ux_record_breakdown
    ON record_breakdown (rollup_date, sport, market, dimension, bucket);
CREATE INDEX ix_record_breakdown_dimension
    ON record_breakdown (sport, dimension, market, rollup_date);
