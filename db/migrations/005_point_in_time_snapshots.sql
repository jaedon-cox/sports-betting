-- Point-in-time input snapshots (Critic must-fix, §3.2): capture inputs,
-- not just model outputs, so backtest reconstruction and leakage audits
-- have something to join against via AsOf (contracts/feature.py).
--
-- All four snapshot tables + raw_snapshots are append-only (§3.1).

CREATE TABLE lineup_snapshots (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id          BIGINT NOT NULL REFERENCES games (id),
    team_id          BIGINT NOT NULL REFERENCES teams (id),
    batting_order    JSONB NOT NULL,
    is_confirmed     BOOLEAN NOT NULL DEFAULT false,
    captured_at_utc  TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_lineup_snapshots_asof ON lineup_snapshots (game_id, team_id, captured_at_utc DESC);

CREATE TRIGGER trg_lineup_snapshots_no_update
    BEFORE UPDATE ON lineup_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
CREATE TRIGGER trg_lineup_snapshots_no_delete
    BEFORE DELETE ON lineup_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TABLE injury_snapshots (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id        TEXT NOT NULL,
    team_id          BIGINT NOT NULL REFERENCES teams (id),
    status           TEXT NOT NULL,
    note             TEXT,
    captured_at_utc  TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_injury_snapshots_asof ON injury_snapshots (player_id, captured_at_utc DESC);

CREATE TRIGGER trg_injury_snapshots_no_update
    BEFORE UPDATE ON injury_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
CREATE TRIGGER trg_injury_snapshots_no_delete
    BEFORE DELETE ON injury_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

CREATE TABLE weather_snapshots (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id          BIGINT NOT NULL REFERENCES games (id),
    temp_f           NUMERIC(5, 1),
    wind_mph         NUMERIC(5, 1),
    wind_dir_deg     SMALLINT CHECK (wind_dir_deg IS NULL OR wind_dir_deg BETWEEN 0 AND 359),
    precip_pct       NUMERIC(5, 2),
    -- Structurally enforces doc §3.7 forecast-only-in-backtests: a
    -- backtest reconstruction must only ever join is_forecast = true rows
    -- captured before the game, never a post-hoc observed reading.
    is_forecast      BOOLEAN NOT NULL,
    captured_at_utc  TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_weather_snapshots_asof ON weather_snapshots (game_id, captured_at_utc DESC);

CREATE TRIGGER trg_weather_snapshots_no_update
    BEFORE UPDATE ON weather_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
CREATE TRIGGER trg_weather_snapshots_no_delete
    BEFORE DELETE ON weather_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

-- ---------------------------------------------------------------------
-- raw_snapshots — full-fidelity archive underneath the typed snapshot
-- tables above. Scoped to point-in-time-sensitive categories only
-- (lineups, injuries, odds, weather) per §3.6 — bulk pybaseball/Statcast
-- pulls are deliberately excluded here (no leakage risk, would dominate
-- the 500 MB free-tier cap).
-- ---------------------------------------------------------------------

CREATE TABLE raw_snapshots (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Forward-compat: this is the table §3.6 flags as the real storage
    -- risk, so being able to filter/prune by sport once a second sport
    -- is live is worth the column even though nothing else here is
    -- sport-keyed.
    sport        TEXT NOT NULL DEFAULT 'mlb',
    source       TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    payload      JSONB NOT NULL,
    pulled_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_raw_snapshots_entity ON raw_snapshots (sport, entity_type, entity_id, pulled_at_utc DESC);

CREATE TRIGGER trg_raw_snapshots_no_update
    BEFORE UPDATE ON raw_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
CREATE TRIGGER trg_raw_snapshots_no_delete
    BEFORE DELETE ON raw_snapshots FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

-- ---------------------------------------------------------------------
-- pipeline_runs — ops health (§3.2). One of the deliberate insert-only
-- exceptions (§3.1): job status transitions are metadata, not a
-- decision-bearing value, so mutating this table doesn't touch the
-- leakage-prevention principle. No append-only guard here by design.
-- Frontend reads this to show "picks pending" instead of an empty state
-- before the day's model_runs flips to success (§2.4).
-- ---------------------------------------------------------------------

CREATE TABLE pipeline_runs (
    run_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running'
                       CHECK (status IN ('running', 'success', 'failed')),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    error_message  TEXT
);

CREATE INDEX ix_pipeline_runs_job_started ON pipeline_runs (job_name, started_at DESC);
