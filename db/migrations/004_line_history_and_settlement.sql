-- Line history & settlement (insert-only, §3.2).
--
-- Book consistency (§5, cross-team contract): picks.market_fair_prob /
-- market_odds_american and pick_settlements.closing_prob must reference
-- the SAME book (Pinnacle) or CLV is not apples-to-apples. Both this
-- table's `source`/`book` default and picks.book default to 'pinnacle'
-- so that invariant holds unless a writer deliberately overrides it.
--
-- De-vig method consistency (main's fix, same reasoning as book
-- consistency): the method is locked per market in markets.devig_method,
-- but this table records which method actually produced THIS row's
-- implied_prob_devigged, so a backtest can prove it even if the
-- configured default changes later — append-only tables can't be
-- back-corrected.

CREATE TABLE line_snapshots (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id                 BIGINT NOT NULL REFERENCES games (id),
    -- Forward-compat: line_snapshots stores a `market` key just like
    -- picks does, so it needs the same (sport, market) composite FK for
    -- referential integrity — see below.
    sport                   TEXT NOT NULL DEFAULT 'mlb',
    market                  TEXT NOT NULL,
    side                    TEXT NOT NULL CHECK (side IN ('home', 'away', 'over', 'under')),
    -- Added by main. Without this column two snapshots of (total, over,
    -- -110) taken at 8.5 and at 9.0 are indistinguishable rows, and CLV --
    -- which is priced against a line, not just a side -- is uncomputable
    -- for two of the three markets. NUMERIC(6, 2) and the NULL-for-
    -- moneyline convention both match picks.line exactly, so a pick and
    -- the snapshot it is graded against compare without a cast.
    line                    NUMERIC(6, 2),
    price_american          INTEGER NOT NULL,
    implied_prob_devigged   NUMERIC(6, 5) CHECK (implied_prob_devigged IS NULL OR implied_prob_devigged BETWEEN 0 AND 1),
    devig_method            TEXT CHECK (devig_method IS NULL OR devig_method IN ('multiplicative', 'power', 'additive', 'shin')),
    captured_at_utc         TIMESTAMPTZ NOT NULL,
    source                  TEXT NOT NULL DEFAULT 'pinnacle',
    is_closing               BOOLEAN NOT NULL DEFAULT false,  -- flags the T-5min close snapshot
    FOREIGN KEY (sport, market) REFERENCES sport_markets (sport, market_key),
    CHECK ((implied_prob_devigged IS NULL) = (devig_method IS NULL))
);

-- Backs "as-of-t" joins: WHERE captured_at_utc <= pick_locked_at
-- ORDER BY captured_at_utc DESC LIMIT 1 (§3.2), and v_pick_clv_live's
-- latest-snapshot-per-game/market/side/book lookup.
CREATE INDEX ix_line_snapshots_asof
    ON line_snapshots (game_id, market, side, source, captured_at_utc DESC);

CREATE TRIGGER trg_line_snapshots_no_update
    BEFORE UPDATE ON line_snapshots
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TRIGGER trg_line_snapshots_no_delete
    BEFORE DELETE ON line_snapshots
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

-- ---------------------------------------------------------------------
-- pick_settlements — insert-once, post-game (§3.2).
-- ---------------------------------------------------------------------

CREATE TABLE pick_settlements (
    pick_id      BIGINT PRIMARY KEY REFERENCES picks (id),
    outcome      TEXT NOT NULL CHECK (outcome IN ('win', 'loss', 'push', 'void')),
    clv_pct      NUMERIC(6, 4),
    closing_prob NUMERIC(6, 5) CHECK (closing_prob IS NULL OR closing_prob BETWEEN 0 AND 1),
    bet_prob     NUMERIC(6, 5) CHECK (bet_prob IS NULL OR bet_prob BETWEEN 0 AND 1),
    settled_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_pick_settlements_no_update
    BEFORE UPDATE ON pick_settlements
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TRIGGER trg_pick_settlements_no_delete
    BEFORE DELETE ON pick_settlements
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
