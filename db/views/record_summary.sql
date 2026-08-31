-- record_summary (§3.3, §4.5): the ONLY place raw picks get aggregated —
-- refreshed by the nightly settlement job (Job F), never at request time.
-- Grain: rollup_date x sport x market, where market carries the literal
-- string 'blended' for the all-markets row instead of the doc's original
-- "NULL = blended" — a plain UNIQUE index (needed for REFRESH
-- ... CONCURRENTLY, §3.3) can't treat two NULLs as a conflict, so ON
-- CONFLICT/concurrent-refresh semantics need a real, non-NULL value.
-- Frontend note (main/frontend notified): read `market = 'blended'` for
-- the all-markets row, not `market IS NULL`.
--
-- Forward-compat: sport is part of the grain (not in the doc's original
-- sketch) so MLB and a future second sport never blend into one number.
--
-- Every aggregate exposes n_evaluated/n_recommended (doc: "every
-- aggregate must expose its N; the frontend shows N next to every
-- stat"). units_staked/units_won/roi_pct are computed over recommended
-- picks only (the actual bet record, in kelly_stake_fraction units —
-- never dollars, §5); avg_clv_pct/avg_edge_pct are averaged over ALL
-- evaluated picks per doc §7 ("CLV on all evaluated games").

CREATE OR REPLACE FUNCTION fn_american_payout_multiplier(odds INTEGER) RETURNS NUMERIC
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN odds IS NULL THEN NULL
        WHEN odds > 0 THEN odds::NUMERIC / 100
        ELSE 100::NUMERIC / ABS(odds)
    END;
$$;

CREATE MATERIALIZED VIEW record_summary AS
WITH agg AS (
    SELECT
        p.game_date AS rollup_date,
        p.sport,
        p.market AS market_raw,  -- NULL only in the blended grouping set below
        COUNT(*) AS n_evaluated,
        COUNT(*) FILTER (WHERE p.recommended) AS n_recommended,
        COUNT(*) FILTER (WHERE p.recommended AND ps.outcome = 'win')  AS wins,
        COUNT(*) FILTER (WHERE p.recommended AND ps.outcome = 'loss') AS losses,
        COUNT(*) FILTER (WHERE p.recommended AND ps.outcome IN ('push', 'void')) AS pushes,
        COALESCE(SUM(p.kelly_stake_fraction) FILTER (WHERE p.recommended), 0) AS units_staked,
        COALESCE(SUM(
            CASE ps.outcome
                WHEN 'win'  THEN p.kelly_stake_fraction * fn_american_payout_multiplier(p.market_odds_american)
                WHEN 'loss' THEN -p.kelly_stake_fraction
                ELSE 0
            END
        ) FILTER (WHERE p.recommended), 0) AS units_won,
        AVG(ps.clv_pct) AS avg_clv_pct,
        AVG((ps.clv_pct > 0)::INT::NUMERIC) AS clv_positive_rate,
        AVG(p.edge_pct) AS avg_edge_pct
    FROM picks p
    JOIN pick_settlements ps ON ps.pick_id = p.id
    GROUP BY GROUPING SETS ((p.game_date, p.sport, p.market), (p.game_date, p.sport))
)
SELECT
    rollup_date,
    sport,
    COALESCE(market_raw, 'blended') AS market,
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

-- Required for REFRESH MATERIALIZED VIEW CONCURRENTLY (§3.3).
CREATE UNIQUE INDEX ux_record_summary ON record_summary (rollup_date, sport, market);
CREATE INDEX ix_record_summary_sport_market ON record_summary (sport, market, rollup_date);
