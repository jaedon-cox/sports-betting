-- v_pick_archive (§3.3, §4.5): keyset-paginated history for the Archive
-- page. Backed by ix_picks_archive_keyset on picks(game_date DESC,
-- market, recommended) (003_picks.sql) — the frontend paginates with
-- `WHERE (game_date, id) < (?, ?) ORDER BY game_date DESC, id DESC LIMIT
-- ?` directly against this view via PostgREST range/limit, no OFFSET.
--
-- LEFT JOINs pick_settlements since a pick isn't settled until its game
-- finishes (§3.2 pick_settlements is insert-once post-game); outcome/
-- clv_pct are NULL for a game still in progress.

CREATE VIEW v_pick_archive WITH (security_invoker = true) AS
SELECT
    p.id, p.game_id, p.game_date, p.sport, p.market, p.side, p.line,
    p.player_id, p.stat_type,
    p.model_prob, p.market_fair_prob, p.market_odds_american, p.book,
    p.edge_pct, p.recommended, p.kelly_stake_fraction, p.pick_locked_at,
    g.external_game_id, g.start_time_utc, g.status AS game_status,
    ht.code AS home_team_code, awt.code AS away_team_code,
    ps.outcome, ps.clv_pct, ps.settled_at
FROM picks p
JOIN games g ON g.id = p.game_id
JOIN teams ht ON ht.id = g.home_team_id
JOIN teams awt ON awt.id = g.away_team_id
LEFT JOIN pick_settlements ps ON ps.pick_id = p.id;
