-- v_todays_picks (§3.3, §4.5): the current slate for the "Today's Picks"
-- page. Flat, one row per pick — the frontend groups client-side by
-- game_id (§4.5) rather than the view nesting anything.
--
-- "Today's" means the latest successful, confirmed run per sport, not a
-- literal join to CURRENT_DATE — run_date is an ET slate-date set by the
-- pipeline, and comparing it against the DB server's date around
-- midnight UTC would misalign. This also directly implements the atomic
-- -publish guarantee (§2.4): a run that died mid-slate never reaches
-- status='success', so it's structurally excluded here and the frontend
-- keeps showing the last known-good complete slate.
--
-- security_invoker: without this, the view runs with the view owner's
-- privileges for RLS purposes and the authenticated-only RLS on picks/
-- games/teams underneath would NOT be enforced for the querying user
-- (Postgres 15+ view option; Supabase's recommended pattern).

CREATE VIEW v_todays_picks WITH (security_invoker = true) AS
WITH latest_run AS (
    SELECT DISTINCT ON (mr.sport)
        mr.id, mr.sport, mr.run_date, mr.pass_type, mr.model_version_id, mr.updated_at
    FROM model_runs mr
    WHERE mr.status = 'success' AND mr.pass_type = 'confirmed'
    ORDER BY mr.sport, mr.run_date DESC, mr.updated_at DESC
)
SELECT
    p.id, p.game_id, p.game_date, p.sport, p.market, p.side, p.line,
    p.player_id, p.stat_type,
    p.raw_model_prob, p.model_prob, p.market_fair_prob, p.market_odds_american, p.book,
    p.edge_pct, p.recommended, p.kelly_stake_fraction, p.pick_locked_at,
    lr.run_date, lr.pass_type, lr.model_version_id,
    g.external_game_id, g.start_time_utc, g.status AS game_status, g.park_name,
    ht.code AS home_team_code, ht.name AS home_team_name,
    awt.code AS away_team_code, awt.name AS away_team_name
FROM latest_run lr
JOIN picks p ON p.model_run_id = lr.id
JOIN games g ON g.id = p.game_id
JOIN teams ht ON ht.id = g.home_team_id
JOIN teams awt ON awt.id = g.away_team_id;
