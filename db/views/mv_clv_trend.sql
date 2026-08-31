-- mv_clv_trend (§3.3, §4.5): cumulative CLV chart, one row per
-- (rollup_date, sport, market) with a running total through that date.
-- Feeds the Model Record page's CLV chart directly — no client-side
-- accumulation needed.
--
-- record_summary stores avg_clv_pct (an average), not a sum, so a naive
-- running AVG-of-AVGs would not compose correctly across days with
-- different pick counts (§3.3 calls this out explicitly: "sum, not
-- average-of-averages"). Since record_summary already exposes
-- n_evaluated, the daily sum is reconstructed as avg_clv_pct *
-- n_evaluated rather than adding a redundant stored sum column, and the
-- cumulative average is the running sum of that divided by the running
-- sum of n_evaluated — a numerator/denominator-weighted composition,
-- not a mean of means.

CREATE MATERIALIZED VIEW mv_clv_trend AS
SELECT
    rollup_date,
    sport,
    market,
    n_evaluated,
    avg_clv_pct,
    SUM(n_evaluated) OVER w AS cum_n_evaluated,
    SUM(avg_clv_pct * n_evaluated) OVER w
        / NULLIF(SUM(n_evaluated) OVER w, 0) AS cum_avg_clv_pct,
    SUM(clv_positive_rate * n_evaluated) OVER w
        / NULLIF(SUM(n_evaluated) OVER w, 0) AS cum_clv_positive_rate
FROM record_summary
WINDOW w AS (PARTITION BY sport, market ORDER BY rollup_date
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

CREATE UNIQUE INDEX ux_mv_clv_trend ON mv_clv_trend (rollup_date, sport, market);
