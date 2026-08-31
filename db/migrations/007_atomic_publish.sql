-- Atomic publish (§2.4): the day's model_runs row starts 'running',
-- writes the full slate's picks, and flips to 'success' as its LAST step,
-- all inside one transaction — so a job that dies partway leaves that
-- run's rows invisible and the frontend keeps showing the last
-- known-good complete slate.
--
-- Implemented as a single Postgres function (called once, over the
-- Supabase PostgREST RPC endpoint) rather than a client-managed
-- BEGIN/COMMIT, so src/sbm/store/ needs no native Postgres driver — it
-- stays on httpx (CLAUDE.md: no new dependency without a note; this is
-- the note). A single top-level function call is one implicit
-- transaction: if any INSERT in the body fails, the whole call — model_runs
-- row included — rolls back, so there is never a stuck 'running' row left
-- behind to clean up. Job-level start/failure visibility for ops still
-- comes from pipeline_runs, which this function does not touch.
--
-- Idempotency (§2.4): re-checks the natural key before inserting, so a
-- retry against an already-'success' run_date/pass_type is a no-op that
-- returns the existing model_run id. The partial unique index on
-- model_runs (001_reference_and_versioning.sql) is the structural
-- backstop against a race between two concurrent publishes.

CREATE OR REPLACE FUNCTION fn_publish_run(
    p_model_version_id  BIGINT,
    p_sport             TEXT,
    p_run_date          DATE,
    p_pass_type         TEXT,
    p_github_run_id     TEXT,
    p_picks             JSONB  -- array of pick objects, one per (game, market)
) RETURNS BIGINT
LANGUAGE plpgsql AS $$
DECLARE
    v_run_id BIGINT;
BEGIN
    SELECT id INTO v_run_id FROM model_runs
    WHERE model_version_id = p_model_version_id
        AND run_date = p_run_date
        AND pass_type = p_pass_type
        AND status = 'success';

    IF v_run_id IS NOT NULL THEN
        RETURN v_run_id;  -- idempotent no-op: already published
    END IF;

    INSERT INTO model_runs (model_version_id, sport, run_date, pass_type, status, github_run_id)
    VALUES (p_model_version_id, p_sport, p_run_date, p_pass_type, 'running', p_github_run_id)
    RETURNING id INTO v_run_id;

    INSERT INTO picks (
        model_run_id, game_id, game_date, sport, market, side, line, player_id, stat_type,
        raw_model_prob, model_prob, market_fair_prob, market_odds_american, book,
        edge_pct, recommended, kelly_stake_fraction, pick_locked_at
    )
    SELECT
        v_run_id,
        (r ->> 'game_id')::BIGINT,
        (r ->> 'game_date')::DATE,
        p_sport,
        r ->> 'market',
        r ->> 'side',
        NULLIF(r ->> 'line', '')::NUMERIC,
        r ->> 'player_id',
        r ->> 'stat_type',
        (r ->> 'raw_model_prob')::NUMERIC,
        (r ->> 'model_prob')::NUMERIC,
        NULLIF(r ->> 'market_fair_prob', '')::NUMERIC,
        NULLIF(r ->> 'market_odds_american', '')::INTEGER,
        COALESCE(r ->> 'book', 'pinnacle'),
        NULLIF(r ->> 'edge_pct', '')::NUMERIC,
        (r ->> 'recommended')::BOOLEAN,
        (r ->> 'kelly_stake_fraction')::NUMERIC,
        (r ->> 'pick_locked_at')::TIMESTAMPTZ
    FROM jsonb_array_elements(p_picks) AS r;

    -- Last step, per §2.4 — flips this run from invisible to the slate
    -- v_todays_picks / today's UI will show.
    UPDATE model_runs SET status = 'success' WHERE id = v_run_id;

    RETURN v_run_id;
END;
$$;
