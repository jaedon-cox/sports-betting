-- slate_status (§4.1 item 7): the honest answer to "what is the state of
-- today's slate", which nothing in the schema could give before.
--
-- v_todays_picks deliberately keeps serving the last known-good complete
-- slate when a run dies mid-publish (§2.4 atomic publish), which is the
-- right behaviour for the picks board and exactly why "rows exist" does
-- NOT mean "today published". The frontend was inferring the difference
-- by counting `games` rows for the ET date, which separates an off-day
-- from a pending slate only by accident: zero games can equally mean the
-- schedule pull never ran, and a non-zero count says nothing about
-- whether the model has published against it. A row the pipeline writes
-- on purpose is the only source that can tell those apart.
--
-- MUTABLE, one row per (sport, slate_date), upserted — NOT append-only,
-- and that is deliberate. §3.1's insert-only invariant has three stated
-- exceptions, of which `pipeline_runs` ("job status transitions") is
-- this table's exact category: a status is ops metadata, not a
-- decision-bearing value, so mutating it cannot corrupt the track record
-- the invariant exists to protect. `pipeline_runs` already keeps the
-- per-job timeline, so an append-only history here would duplicate
-- evidence rather than add any. (`db` first specced this append-only
-- with a latest-row view over it; `pipeline` had independently built the
-- writer against upsert semantics with the reasoning above, which is the
-- doc's own reading, so the DDL converged on theirs. The write path is
-- src/sbm/jobs/slate.py and is the only writer — there is deliberately
-- no second one in src/sbm/store/.)
--
-- The status vocabulary is the frontend's, 1:1 with what §4.1 item 7
-- renders, so nothing has to translate between the DB's states and the
-- UI's: an off-day, a pending slate, a published one, a failed run.

CREATE TABLE slate_status (
    sport         TEXT NOT NULL DEFAULT 'mlb',
    -- ET slate-date, the same key as picks.game_date / games.game_date /
    -- model_runs.run_date — NOT a UTC date. Comparing against the DB
    -- server's CURRENT_DATE around midnight UTC would misalign, which is
    -- the same reason v_todays_picks resolves "today" through the latest
    -- successful run rather than a date literal.
    slate_date    DATE NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('no_games', 'pending', 'published', 'failed')),
    n_games       INTEGER NOT NULL DEFAULT 0 CHECK (n_games >= 0),
    -- Set by 'published' only. Lets the frontend read the publish time
    -- from model_runs.updated_at for the "generated at HH:MM ET" banner
    -- without guessing which run produced the board.
    model_run_id  BIGINT REFERENCES model_runs (id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Not redundant with slate_date: a 'pending' row that has not moved
    -- in six hours is a dead pipeline, and the date alone cannot say so.
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The upsert conflict target (src/sbm/jobs/slate.py's ON_CONFLICT),
    -- and the read key: one row per sport per slate date.
    PRIMARY KEY (sport, slate_date),
    -- An off-day claim with games on it is a bug, not a state. Structural
    -- rather than trusted-by-convention because this column is the whole
    -- reason the table exists.
    CHECK (status <> 'no_games' OR n_games = 0),
    -- Likewise: 'published' must point at the run it published, so the
    -- frontend's banner and v_todays_picks can never disagree about
    -- which slate is live.
    CHECK (status <> 'published' OR model_run_id IS NOT NULL)
);

CREATE TRIGGER trg_slate_status_touch_updated_at
    BEFORE UPDATE ON slate_status
    FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();
