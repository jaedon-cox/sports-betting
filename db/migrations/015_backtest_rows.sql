-- fn_backtest_rows — the flat open/close join Job G assembles
-- BacktestGames from (src/sbm/jobs/job_g_backtest.py).
--
-- One row per (game, market, side) carrying both prices, per that
-- module's request: db writes a plain join, the job does the assembly.
--
-- INNER JOINs throughout, and that is the point. A backtest game needs a
-- bet-time price, a closing price for the same side from the same book,
-- and a final score; a row missing any of those is not a partial result
-- to be patched over downstream, it is a game that cannot be backtested.
-- run_backtest raises on an empty game list rather than reporting a NaN
-- CLV over zero picks, so excluding here surfaces as that loud failure
-- rather than as a quietly thinner sample.
--
-- Expect this to return nothing until the system has captured its own
-- line history. That is backend doc §7 item 3 (no free source of
-- historical Pinnacle closing lines was found), not a defect in this
-- query — the only usable history is what Jobs A and E capture going
-- forward.
--
-- p_source defaults to 'pinnacle' and scopes BOTH sides of the open/
-- close pair: a CLV computed from one book's open against another's
-- close is not apples-to-apples (§5 book consistency), and a backtest is
-- the one place that error would be invisible.

CREATE OR REPLACE FUNCTION fn_backtest_rows(
    p_sport   TEXT,
    p_from    DATE,
    p_to      DATE,
    p_source  TEXT DEFAULT 'pinnacle'
) RETURNS TABLE (
    external_game_id      TEXT,
    game_date             DATE,
    as_of_utc             TIMESTAMPTZ,
    market                TEXT,
    side                  TEXT,
    open_line             NUMERIC,
    open_price_american   INTEGER,
    close_line            NUMERIC,
    close_price_american  INTEGER,
    home_score            INTEGER,
    away_score            INTEGER
)
LANGUAGE sql STABLE AS $$
    WITH opens AS (
        -- Earliest NON-closing snapshot per side. Excluding is_closing
        -- matters: if a sweep captured only a close, taking "the earliest
        -- snapshot" would make open and close the same row and report a
        -- fabricated CLV of exactly zero for that game.
        SELECT DISTINCT ON (ls.game_id, ls.market, ls.side)
            ls.game_id, ls.market, ls.side, ls.line, ls.price_american, ls.captured_at_utc
        FROM line_snapshots ls
        WHERE ls.sport = p_sport AND ls.source = p_source AND NOT ls.is_closing
        ORDER BY ls.game_id, ls.market, ls.side, ls.captured_at_utc, ls.id
    ),
    closes AS (
        SELECT DISTINCT ON (ls.game_id, ls.market, ls.side)
            ls.game_id, ls.market, ls.side, ls.line, ls.price_american
        FROM line_snapshots ls
        WHERE ls.sport = p_sport AND ls.source = p_source AND ls.is_closing
        ORDER BY ls.game_id, ls.market, ls.side, ls.captured_at_utc DESC, ls.id DESC
    )
    SELECT
        g.external_game_id,
        g.game_date,
        -- One as_of for the whole game, since BacktestGame carries a
        -- single one for all its quotes. The EARLIEST open across the
        -- game's markets, not this row's own: features rebuilt at that
        -- instant were knowable at every later price too, so the
        -- conservative direction is the only one that cannot leak
        -- (CLAUDE.md rule 4). In practice the three markets come from one
        -- Odds API call (§2.5) and share a timestamp, so this is a
        -- guardrail rather than a routine correction.
        MIN(o.captured_at_utc) OVER (PARTITION BY g.id) AS as_of_utc,
        o.market, o.side,
        o.line, o.price_american,
        c.line, c.price_american,
        r.home_score, r.away_score
    FROM games g
    JOIN results r ON r.game_id = g.id AND r.final_status = 'final'
    JOIN opens  o ON o.game_id = g.id
    JOIN closes c ON c.game_id = g.id AND c.market = o.market AND c.side = o.side
    WHERE g.sport = p_sport
      AND g.game_date BETWEEN p_from AND p_to
    ORDER BY g.game_date, g.external_game_id, o.market, o.side;
$$;
