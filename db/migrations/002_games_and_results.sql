-- Games & results.
--
-- games is normal mutable reference state (schedule, status progression);
-- it is NOT in the doc's §3.1 append-only list. results is insert-once at
-- final (§3.1) and gets the append-only guard.

CREATE TABLE games (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Forward-compat (main's request): denormalized so every downstream
    -- query/index can filter by sport without a join, and so external ids
    -- from different providers can't collide across sports (see the
    -- external_game_id UNIQUE constraint below).
    sport             TEXT NOT NULL DEFAULT 'mlb',
    external_game_id  TEXT NOT NULL,  -- e.g. MLB StatsAPI gamePk; upsert key
    game_date         DATE NOT NULL,  -- ET slate-date
    start_time_utc    TIMESTAMPTZ,
    home_team_id      BIGINT NOT NULL REFERENCES teams (id),
    away_team_id      BIGINT NOT NULL REFERENCES teams (id),
    park_name         TEXT,
    status            TEXT NOT NULL DEFAULT 'scheduled'
                          CHECK (status IN ('scheduled', 'in_progress', 'final', 'postponed', 'cancelled')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Forward-compat: was a bare UNIQUE on external_game_id in the doc's
    -- sketch. Two sports' schedule providers can independently emit
    -- overlapping id spaces (e.g. both using small sequential integers),
    -- so the upsert/uniqueness key is scoped per sport.
    UNIQUE (sport, external_game_id)
);

CREATE INDEX ix_games_sport_game_date ON games (sport, game_date);

CREATE TRIGGER trg_games_touch_updated_at
    BEFORE UPDATE ON games
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- ---------------------------------------------------------------------
-- results
--
-- Sport-neutral score representation (main notified): the doc's sketch
-- had `home_runs`/`away_runs`, which is baseball-shaped and would need a
-- migration the day NFL/NBA land. Replaced with generic `home_score`/
-- `away_score` — the two integers every team market (moneyline/spread/
-- total) settlement needs regardless of sport — plus a nullable `detail`
-- JSONB for sport-specific extras that settlement math doesn't need
-- (MLB extra-innings flag, NFL/NBA overtime periods, box-score periods).
-- This keeps settlement logic generic while not discarding richness.
-- ---------------------------------------------------------------------

CREATE TABLE results (
    game_id       BIGINT PRIMARY KEY REFERENCES games (id),
    home_score    INTEGER NOT NULL,
    away_score    INTEGER NOT NULL,
    detail        JSONB,  -- sport-specific extras; never read by settlement math
    final_status  TEXT NOT NULL CHECK (final_status IN ('final', 'postponed', 'cancelled')),
    settled_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_results_no_update
    BEFORE UPDATE ON results
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TRIGGER trg_results_no_delete
    BEFORE DELETE ON results
    FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
