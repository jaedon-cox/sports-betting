-- The two point-in-time reads `pipeline` needs, as named functions.
--
-- src/sbm/store/ is write-only by design (§4.5: "Reads for the frontend
-- go straight to Postgres ... there is no REST read layer in this
-- package") and PostgrestClient exposes no filtered select. So each read
-- the pipeline actually needs is one named function over /rpc, following
-- fn_odds_budget_month_total's precedent — deliberately not a
-- general-purpose query builder, which would let any job invent its own
-- point-in-time semantics. The as-of discipline below is the whole
-- reason these are functions and not client-side filters.
--
-- Consumed by src/sbm/jobs/reads.py; the column names below are the
-- contract with that module's LineQuote / UnsettledPick dataclasses.
-- Grants are in db/policies/004_wave2_read_surface.sql.

-- ---------------------------------------------------------------------
-- fn_latest_lines — latest snapshot per (game, market, side) at or
-- before p_as_of, for one slate date.
--
-- The as-of bound is the point (§3.2: `WHERE captured_at_utc <= ...
-- ORDER BY captured_at_utc DESC LIMIT 1`, CLAUDE.md rule 4). A pick
-- priced against a snapshot taken after it was locked makes its own CLV
-- meaningless, and doing the filter here rather than in Python means no
-- job can skip it.
--
-- p_source defaults to 'pinnacle' and is part of the DISTINCT ON key's
-- filter rather than its grouping: book consistency (§5) requires that a
-- pick's generation price and its close come from the SAME book, so this
-- returns one book's view of the slate, never a mixture. Callers that
-- omit the argument get Pinnacle, which is every caller today.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_latest_lines(
    p_sport      TEXT,
    p_game_date  DATE,
    p_as_of      TIMESTAMPTZ,
    p_source     TEXT DEFAULT 'pinnacle'
) RETURNS TABLE (
    game_id                BIGINT,
    market                 TEXT,
    side                   TEXT,
    line                   NUMERIC,
    price_american         INTEGER,
    implied_prob_devigged  NUMERIC,
    devig_method           TEXT,
    captured_at_utc        TIMESTAMPTZ,
    is_closing             BOOLEAN
)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (ls.game_id, ls.market, ls.side)
        ls.game_id, ls.market, ls.side, ls.line, ls.price_american,
        ls.implied_prob_devigged, ls.devig_method, ls.captured_at_utc, ls.is_closing
    FROM line_snapshots ls
    JOIN games g ON g.id = ls.game_id
    WHERE ls.sport = p_sport
      AND g.game_date = p_game_date
      AND ls.source = p_source
      AND ls.captured_at_utc <= p_as_of
    ORDER BY ls.game_id, ls.market, ls.side, ls.captured_at_utc DESC, ls.id DESC;
$$;

-- ---------------------------------------------------------------------
-- fn_unsettled_picks — picks on terminal games with no pick_settlements
-- row yet, for Job F.
--
-- Idempotency comes from the absence of a settlement row, not from a
-- date filter: a rerun after a partial night settles only what is still
-- missing, and pick_settlements is insert-once so a second insert would
-- be a primary-key violation rather than an overwrite. p_before is only
-- a safety bound (don't try to settle a game that has not started).
--
-- p_before bounds games.start_time_utc, NOT picks.pick_locked_at —
-- settled by the lead after `db` and `pipeline` could not agree, so
-- treat this as decided rather than reopening it. Job F settles games
-- that have finished, so the cutoff has to be a property of the game.
-- Bounding pick_locked_at would return every pick locked before the
-- cutoff whose game has not been played yet — all of them unsettleable —
-- and an early-locked pick for a late game would be pulled into every
-- subsequent run forever.
--
-- closing_prob/closing_line come from the is_closing snapshot for the
-- pick's OWN side and book — the same side bet_prob (picks
-- .market_fair_prob) refers to, or the CLV computed from the pair would
-- compare a side against its complement. NULL when no close was
-- captured (a postponed game, a missed sweep); that is a null row for
-- Job F to handle, never an error here.
--
-- Terminal statuses include postponed/cancelled so Job F can void those
-- picks rather than leave them unsettled forever, which would make them
-- accumulate in every subsequent night's result set.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_unsettled_picks(
    p_sport   TEXT,
    p_before  TIMESTAMPTZ
) RETURNS TABLE (
    pick_id       BIGINT,
    game_id       BIGINT,
    market        TEXT,
    side          TEXT,
    line          NUMERIC,
    bet_prob      NUMERIC,
    model_prob    NUMERIC,
    game_status   TEXT,
    home_score    INTEGER,
    away_score    INTEGER,
    game_date     DATE,
    closing_prob  NUMERIC,
    closing_line  NUMERIC
)
LANGUAGE sql STABLE AS $$
    SELECT
        p.id, p.game_id, p.market, p.side, p.line,
        p.market_fair_prob, p.model_prob,
        g.status, r.home_score, r.away_score, p.game_date,
        cl.implied_prob_devigged, cl.line
    FROM picks p
    JOIN games g ON g.id = p.game_id
    LEFT JOIN results r ON r.game_id = g.id
    LEFT JOIN LATERAL (
        SELECT x.implied_prob_devigged, x.line
        FROM line_snapshots x
        WHERE x.game_id = p.game_id AND x.market = p.market
          AND x.side = p.side AND x.source = p.book
          AND x.is_closing
        ORDER BY x.captured_at_utc DESC, x.id DESC
        LIMIT 1
    ) cl ON true
    WHERE p.sport = p_sport
      AND g.status IN ('final', 'postponed', 'cancelled')
      -- NULL start_time_utc means the schedule row is incomplete; a
      -- terminal game with no start time is still settleable, so it is
      -- included rather than silently stranded.
      AND (g.start_time_utc IS NULL OR g.start_time_utc < p_before)
      AND NOT EXISTS (SELECT 1 FROM pick_settlements ps WHERE ps.pick_id = p.id)
    ORDER BY p.game_date, p.game_id, p.market, p.side;
$$;
