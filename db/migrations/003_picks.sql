-- Picks: core append-only fact table (§3.2). Favored side only — the NB
-- joint distribution makes sides complementary, so one row per
-- (game, market, run) is the full record.

CREATE TABLE picks (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_run_id           BIGINT NOT NULL REFERENCES model_runs (id),
    game_id                BIGINT NOT NULL REFERENCES games (id),
    game_date              DATE NOT NULL,  -- denormalized for index-only archive reads
    -- Forward-compat (main's request): denormalized like game_date, for
    -- the same index-only-archive reasoning, and because it's the column
    -- every rollup (record_summary etc.) groups by.
    sport                  TEXT NOT NULL DEFAULT 'mlb',
    -- Forward-compat (main's request): was `CHECK IN ('moneyline','total',
    -- 'run_line')` in the doc's sketch. A hard-coded enum blocks player
    -- props and every future sport's markets. Now FK'd through
    -- sport_markets so (sport, market) must be a real, currently-priced
    -- combination — see the composite FK below and fn_validate_pick().
    market                 TEXT NOT NULL,
    side                   TEXT NOT NULL CHECK (side IN ('home', 'away', 'over', 'under')),
    line                   NUMERIC(6, 2),  -- spread/total number (e.g. -1.5, 8.5); NULL for moneyline
    -- Forward-compat (main's request): nullable prop columns so a player
    -- prop fits this same table later with zero migration. NULL for every
    -- current MLB team-market pick; fn_validate_pick() enforces they are
    -- non-null exactly when the market is a prop (required_dims = 1).
    player_id              TEXT,
    stat_type               TEXT,
    raw_model_prob         NUMERIC(6, 5) NOT NULL CHECK (raw_model_prob BETWEEN 0 AND 1),
    model_prob              NUMERIC(6, 5) NOT NULL CHECK (model_prob BETWEEN 0 AND 1),
    market_fair_prob        NUMERIC(6, 5) CHECK (market_fair_prob IS NULL OR market_fair_prob BETWEEN 0 AND 1),
    -- De-vig method that actually produced market_fair_prob on THIS row
    -- (main's fix, core's bug report): markets.devig_method is the
    -- configured default, but picks is append-only, so if that default
    -- ever changes, only recording it here — not recomputing history —
    -- lets a backtest prove which method generated a given number.
    -- Required exactly when market_fair_prob is present.
    devig_method             TEXT CHECK (devig_method IS NULL OR devig_method IN ('multiplicative', 'power', 'additive', 'shin')),
    market_odds_american    INTEGER,
    book                    TEXT NOT NULL DEFAULT 'pinnacle',
    -- NUMERIC(6,5), not (6,4): edge_pct = model_prob - market_fair_prob,
    -- a direct subtraction of two NUMERIC(6,5) columns, so rounding it to
    -- 4 decimals would throw away real precision from its own inputs
    -- (core's correction). Signed — can be negative; recommended=false
    -- rows are kept specifically to track CLV on below-threshold edges
    -- too (doc §7).
    edge_pct                NUMERIC(6, 5) CHECK (edge_pct IS NULL OR edge_pct BETWEEN -1 AND 1),
    recommended             BOOLEAN NOT NULL,  -- false rows kept -> CLV on ALL evaluated games (doc §7)
    kelly_stake_fraction     NUMERIC(6, 4) NOT NULL DEFAULT 0
                                 CHECK (kelly_stake_fraction BETWEEN 0 AND 1),  -- % of bankroll ONLY, never $ (§5)
    pick_locked_at           TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, market, model_run_id),
    FOREIGN KEY (sport, market) REFERENCES sport_markets (sport, market_key),
    CHECK ((market_fair_prob IS NULL) = (devig_method IS NULL))
);

-- Backs v_pick_archive's keyset pagination: WHERE (game_date, id) < (?, ?)
-- ORDER BY game_date DESC, id DESC (§3.3).
CREATE INDEX ix_picks_archive_keyset ON picks (game_date DESC, market, recommended);
CREATE INDEX ix_picks_model_run_id ON picks (model_run_id);
CREATE INDEX ix_picks_game_id ON picks (game_id);

-- Validates side and prop-field nullability against the markets lookup
-- instead of hard-coding market names into a CHECK (which is exactly the
-- kind of enum this migration is trying to eliminate). A market's legal
-- `side` values live in markets.sides (e.g. total -> {over,under},
-- moneyline -> {home,away}); its required_dims says whether player_id/
-- stat_type must be present. This one trigger replaces both the doc's
-- "total <-> over/under" CHECK and the new prop-field CHECK, and it
-- generalizes correctly to any future market without another migration.
CREATE OR REPLACE FUNCTION fn_validate_pick() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_required_dims SMALLINT;
    v_sides TEXT[];
BEGIN
    SELECT required_dims, sides INTO v_required_dims, v_sides
    FROM markets WHERE key = NEW.market;

    -- Without this, an unrecognized market key leaves v_required_dims/
    -- v_sides NULL, every comparison below evaluates to NULL (neither
    -- true nor false in plpgsql's three-valued IF), and this trigger
    -- would silently no-op instead of raising — the row would then only
    -- fail on the (sport, market) FK below, with a far less useful error.
    IF NOT FOUND THEN
        RAISE EXCEPTION 'market=% is not a recognized market key', NEW.market;
    END IF;

    IF NOT (NEW.side = ANY (v_sides)) THEN
        RAISE EXCEPTION 'side=% is not valid for market=% (legal sides: %)',
            NEW.side, NEW.market, v_sides;
    END IF;

    IF v_required_dims = 1 THEN  -- player prop
        IF NEW.player_id IS NULL OR NEW.stat_type IS NULL THEN
            RAISE EXCEPTION 'market=% is a player prop: player_id and stat_type are required', NEW.market;
        END IF;
    ELSE  -- team market
        IF NEW.player_id IS NOT NULL OR NEW.stat_type IS NOT NULL THEN
            RAISE EXCEPTION 'market=% is a team market: player_id and stat_type must be NULL', NEW.market;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_picks_validate
    BEFORE INSERT ON picks
    FOR EACH ROW EXECUTE FUNCTION fn_validate_pick();

CREATE TRIGGER trg_picks_no_update
    BEFORE UPDATE ON picks
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TRIGGER trg_picks_no_delete
    BEFORE DELETE ON picks
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
