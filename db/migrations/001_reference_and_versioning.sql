-- Reference / versioning: shared utility functions, model_versions, markets
-- lookup + sport_markets junction, teams, model_runs.
--
-- See docs/backend-frontend-database-planning.md §3.1-§3.2 for the source
-- schema sketch and CLAUDE.md rule 5 for the insert-only invariant.

-- ---------------------------------------------------------------------
-- Shared utility functions (used by every insert-only / mutable table
-- migrated after this file).
-- ---------------------------------------------------------------------

-- Attached as a BEFORE UPDATE/DELETE trigger to every append-only table
-- (picks, line_snapshots, results, pick_settlements, the point-in-time
-- snapshot tables). New facts are new rows — corrections are a new
-- model_run, never a mutation (§3.1, CLAUDE.md rule 5).
CREATE OR REPLACE FUNCTION fn_reject_mutation() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % is not permitted: this table is insert-only (CLAUDE.md rule 5)',
        TG_OP, TG_TABLE_NAME;
END;
$$;

-- Attached as a BEFORE UPDATE trigger to mutable tables that track their
-- own freshness (games, model_runs, pipeline_runs, user_settings, profiles,
-- calibration_buckets).
CREATE OR REPLACE FUNCTION fn_touch_updated_at() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------
-- model_versions
-- ---------------------------------------------------------------------

CREATE TABLE model_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Forward-compat: sport added so a monorepo commit that touches more
    -- than one sport's model can register a version row per sport without
    -- git_sha collisions. Not in the doc's original sketch (main notified).
    sport         TEXT NOT NULL DEFAULT 'mlb',
    git_sha       TEXT NOT NULL,
    semver_label  TEXT,
    config_hash   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sport, git_sha)
);

-- ---------------------------------------------------------------------
-- markets lookup + sport_markets junction
--
-- Forward-compat (main's request): replaces the doc's
-- `picks.market CHECK IN ('moneyline','total','run_line')` enum, which
-- would have blocked player props and every future sport. A market row
-- is sport-agnostic (moneyline exists in MLB, NFL, NBA alike); the
-- junction table is what says which sports currently price which
-- markets, without ever touching this schema again to add one.
--
-- Key correction (core + model + main, independently): the MLB "run
-- line" is not its own market — `markets/spread.py` registers under the
-- generic key "spread" with line=±1.5 (CLAUDE.md rule 7: shared code
-- must not know MLB's product names). The lookup row below carries the
-- MLB-facing label ("Run Line") while `Market.key`/`picks.market` store
-- the generic "spread" — an NFL spread is the same row shape with a
-- different display_name, not a different key.
-- ---------------------------------------------------------------------

CREATE TABLE markets (
    key            TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    -- Mirrors contracts/market.py Market.required_dims: 2 for team
    -- (joint home/away) markets, 1 for player props.
    required_dims  SMALLINT NOT NULL CHECK (required_dims IN (1, 2)),
    -- Mirrors contracts/market.py Market.sides — the legal `side` values
    -- for this market, in complementary order.
    sides          TEXT[] NOT NULL,
    -- De-vig method LOCKED per market (main's fix): core found the
    -- previous per-price method selection could de-vig the same pick's
    -- open and close differently, injecting a ~78bps CLV artifact. This
    -- is the single source of truth for "which method to use for this
    -- market" — line_snapshots.devig_method and picks.devig_method
    -- (004/003) record which method actually produced a given row's
    -- number, so a backtest can prove it without an append-only table
    -- ever needing a correction.
    --
    -- Value set is core's (`core.pricing._METHODS`), not data — the four
    -- legal values are 'multiplicative', 'power', 'additive', 'shin'.
    -- Widened from a two-value CHECK after main/core's follow-up: model
    -- doc §7's original moneyline-vs-totals split rested on a disproven
    -- premise (the "additive understates the favorite at extreme prices"
    -- rationale only applies to 3+ outcome books; core verified over 50k
    -- simulated 2-way books that additive tracks power almost exactly and
    -- never produces the claimed failure mode for n=2). main's actual
    -- call: 'power' for all three current MLB markets, one method
    -- everywhere — also matters because record_summary/mv_clv_trend
    -- blend CLV across markets, and per-market methods would mix method
    -- artifacts into that blend, the same defect one level up.
    devig_method   TEXT NOT NULL CHECK (devig_method IN ('multiplicative', 'power', 'additive', 'shin')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sport_markets (
    sport       TEXT NOT NULL,
    market_key  TEXT NOT NULL REFERENCES markets (key),
    PRIMARY KEY (sport, market_key)
);

-- Seed: the three MLB markets the model prices today (model doc A2/A3).
-- Adding a fourth market or a second sport is a data insert here, never
-- a schema change. devig_method is 'power' for all three per main's
-- decision above — not a per-market split.
INSERT INTO markets (key, display_name, required_dims, sides, devig_method) VALUES
    ('moneyline', 'Moneyline', 2, ARRAY['home', 'away'], 'power'),
    ('total',     'Run Total', 2, ARRAY['over', 'under'], 'power'),
    ('spread',    'Run Line',  2, ARRAY['home', 'away'], 'power');

INSERT INTO sport_markets (sport, market_key) VALUES
    ('mlb', 'moneyline'),
    ('mlb', 'total'),
    ('mlb', 'spread');

-- ---------------------------------------------------------------------
-- teams
--
-- Not seeded here deliberately — team codes/names/divisions are live
-- data owned by the ingest source (MLB StatsAPI), not something this
-- migration should guess at or let go stale. `ingest` upserts via
-- src/sbm/store's upsert_teams().
-- ---------------------------------------------------------------------

CREATE TABLE teams (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Forward-compat: a bare `code UNIQUE` (the doc's original shape)
    -- breaks the moment two sports' team codes collide (e.g. 'TB' for
    -- both Tampa Bay Rays and Buccaneers). Scoped per sport instead.
    sport       TEXT NOT NULL DEFAULT 'mlb',
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    league      TEXT,
    division    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sport, code)
);

-- ---------------------------------------------------------------------
-- model_runs
--
-- One row per (model_version, run_date, pass_type) covering the whole
-- day's slate — not per game — so atomic-publish is a single-row status
-- check (§2.4). The running -> success flip is the one deliberate
-- exception to insert-only (§3.1); fn_guard_model_runs_update() below
-- enforces that it's the *only* legal mutation.
-- ---------------------------------------------------------------------

CREATE TABLE model_runs (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_version_id  BIGINT NOT NULL REFERENCES model_versions (id),
    -- Forward-compat: denormalized from model_versions so "today's MLB
    -- runs" doesn't require a join; also lets model_runs stay meaningful
    -- if a future model_version genuinely spans sports.
    sport             TEXT NOT NULL DEFAULT 'mlb',
    run_date          DATE NOT NULL,
    pass_type         TEXT NOT NULL CHECK (pass_type IN ('projected', 'confirmed')),
    status            TEXT NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running', 'success', 'failed', 'partial')),
    github_run_id     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotency (§2.4): natural key is (model_version, run_date, pass_type).
-- A partial unique index on successful rows makes duplicate successful
-- runs structurally impossible, while still allowing multiple failed/
-- running attempts to coexist for the same natural key (each retry is a
-- new row; fn_publish_run in 007_atomic_publish.sql checks this before
-- inserting so retries no-op instead of racing).
CREATE UNIQUE INDEX ux_model_runs_success_natural_key
    ON model_runs (model_version_id, run_date, pass_type)
    WHERE status = 'success';

CREATE INDEX ix_model_runs_sport_run_date ON model_runs (sport, run_date DESC);

-- Enforces the §3.1 exception precisely: only a row currently 'running'
-- may be updated at all, identity columns may never change, and any
-- update (i.e. the running->success/failed/partial flip) touches
-- updated_at. Once a row leaves 'running' it is as immutable as picks.
CREATE OR REPLACE FUNCTION fn_guard_model_runs_update() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'running' THEN
        RAISE EXCEPTION
            'model_runs.id=% is terminal (status=%): only the running->success/failed/partial flip is a legal mutation (§3.1)',
            OLD.id, OLD.status;
    END IF;
    IF NEW.model_version_id <> OLD.model_version_id
        OR NEW.run_date <> OLD.run_date
        OR NEW.pass_type <> OLD.pass_type
        OR NEW.created_at <> OLD.created_at
    THEN
        RAISE EXCEPTION 'model_runs identity columns (model_version_id, run_date, pass_type, created_at) are immutable';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_model_runs_guard
    BEFORE UPDATE ON model_runs
    FOR EACH ROW EXECUTE FUNCTION fn_guard_model_runs_update();
