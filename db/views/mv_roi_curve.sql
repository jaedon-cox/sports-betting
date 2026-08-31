-- mv_roi_curve (§3.3, §4.5): cumulative ROI chart, mirroring
-- mv_clv_trend's structure. ROI is subordinated to CLV as the gate
-- metric (CLAUDE.md, doc §6) but still tracked — units are
-- kelly_stake_fraction-derived (% of bankroll), never dollars (§5).
-- cum_roi_pct is cum_units_won / cum_units_staked, the correct
-- composition (not an average of daily roi_pct values, which would
-- overweight low-volume days).

CREATE MATERIALIZED VIEW mv_roi_curve AS
SELECT
    rollup_date,
    sport,
    market,
    n_recommended,
    units_staked,
    units_won,
    roi_pct,
    SUM(n_recommended) OVER w AS cum_n_recommended,
    SUM(units_staked) OVER w AS cum_units_staked,
    SUM(units_won) OVER w AS cum_units_won,
    CASE WHEN SUM(units_staked) OVER w = 0 THEN NULL
         ELSE SUM(units_won) OVER w / SUM(units_staked) OVER w
    END AS cum_roi_pct
FROM record_summary
WINDOW w AS (PARTITION BY sport, market ORDER BY rollup_date
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

CREATE UNIQUE INDEX ux_mv_roi_curve ON mv_roi_curve (rollup_date, sport, market);
