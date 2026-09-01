-- v_pick_clv_live (§3.3, §4.5): Pick Detail page. Live/pre-settlement CLV
-- computed from the pick's own locked-in fair price vs. the most recent
-- line_snapshot for the same game/market/side/book — useful before
-- pick_settlements exists (a game still in progress) or for a quick
-- sanity check afterward. The frontend combines this with a direct read
-- of pick_settlements and the open/close line_snapshots rows for the
-- full detail view (§4.5) — this view is the "live" number, not the
-- final one.
--
-- ---------------------------------------------------------------------
-- UNITS. Read this before using either CLV column anywhere.
--
-- There are TWO CLV numbers in this schema and they are NOT the same
-- quantity. At typical prices they are roughly 2x apart, and they used
-- to share a name-shape (`clv_pct` / `clv_pct_live`), which made mixing
-- them a one-character mistake. The live column is now named for its
-- units so that can't happen:
--
--   RELATIVE  pick_settlements.clv_pct
--             = (closing_prob - bet_prob) / bet_prob
--             a fraction OF THE BET'S OWN PRICE. Defined once, in
--             src/sbm/core/clv.py (compute_clv) — that function is the
--             single source of truth for "CLV pct" in this system, and
--             it is what record_summary.avg_clv_pct and therefore
--             mv_clv_trend aggregate. Settled picks only.
--
--   ABSOLUTE  v_pick_clv_live.clv_abs_live   (this file, below)
--             = latest_fair_prob - locked_fair_prob
--             a difference IN PROBABILITY POINTS. 0.0040 = 40 bps of
--             win probability. Live / pre-settlement only; it is never
--             aggregated into any rollup.
--
-- Worked example of the ~2x gap: a bet at fair 0.50 that closes at 0.52
-- is +0.020 absolute (200 bps) but +4.0% relative — and the same +0.020
-- move from 0.20 to 0.22 is +10.0% relative. Relative depends on the
-- price you took; absolute does not. Averaging, comparing or co-plotting
-- one against the other is always wrong.
--
-- Deliberately NOT reconciled to one unit: the relative definition needs
-- a settled bet_prob and the whole point of this view is to have a
-- number before settlement exists. Both are kept; only the names are
-- made honest. The frontend enforces the same separation with branded
-- types in web/src/lib/clv.ts.
-- ---------------------------------------------------------------------
--
-- Book consistency (§5): the lateral join is scoped to
-- `line_snapshots.source = picks.book` so this never mixes books
-- between the pick's generation price and the snapshot used for the
-- live CLV read.

CREATE VIEW v_pick_clv_live WITH (security_invoker = true) AS
SELECT
    p.id AS pick_id, p.game_id, p.sport, p.market, p.side, p.line, p.book,
    p.market_fair_prob AS locked_fair_prob,
    p.market_odds_american AS locked_odds_american,
    p.pick_locked_at,
    ls.price_american AS latest_odds_american,
    ls.implied_prob_devigged AS latest_fair_prob,
    ls.captured_at_utc AS latest_captured_at,
    ls.is_closing AS latest_is_closing,
    -- ABSOLUTE: probability points, not a fraction of the bet price.
    -- See the units block above before touching this expression.
    CASE
        WHEN ls.implied_prob_devigged IS NOT NULL AND p.market_fair_prob IS NOT NULL
            THEN ls.implied_prob_devigged - p.market_fair_prob
    END AS clv_abs_live
FROM picks p
LEFT JOIN LATERAL (
    SELECT price_american, implied_prob_devigged, captured_at_utc, is_closing
    FROM line_snapshots x
    WHERE x.game_id = p.game_id AND x.market = p.market AND x.side = p.side AND x.source = p.book
    ORDER BY x.captured_at_utc DESC
    LIMIT 1
) ls ON true;
