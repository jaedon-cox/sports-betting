-- v_pick_clv_live (§3.3, §4.5): Pick Detail page. Live/pre-settlement CLV
-- computed from the pick's own locked-in fair price vs. the most recent
-- line_snapshot for the same game/market/side/book — useful before
-- pick_settlements exists (a game still in progress) or for a quick
-- sanity check afterward. The frontend combines this with a direct read
-- of pick_settlements and the open/close line_snapshots rows for the
-- full detail view (§4.5) — this view is the "live" number, not the
-- final one.
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
    CASE
        WHEN ls.implied_prob_devigged IS NOT NULL AND p.market_fair_prob IS NOT NULL
            THEN ls.implied_prob_devigged - p.market_fair_prob
    END AS clv_pct_live
FROM picks p
LEFT JOIN LATERAL (
    SELECT price_american, implied_prob_devigged, captured_at_utc, is_closing
    FROM line_snapshots x
    WHERE x.game_id = p.game_id AND x.market = p.market AND x.side = p.side AND x.source = p.book
    ORDER BY x.captured_at_utc DESC
    LIMIT 1
) ls ON true;
