-- BUG FIX (found by `pipeline` building Job C/D): fn_publish_run could
-- not publish any pick that carried a de-vigged market price — i.e.
-- every priced pick, which is every recommended pick.
--
-- 003_picks.sql added `picks.devig_method` with
-- `CHECK ((market_fair_prob IS NULL) = (devig_method IS NULL))`, so the
-- two columns must both be set or both be NULL. 007_atomic_publish.sql's
-- INSERT column list never included devig_method, so every row it built
-- with a market_fair_prob had devig_method NULL and violated that CHECK.
-- Because the whole slate publishes in one transaction, one such row
-- rolled back the entire run — model_runs row included. Only a pick with
-- market_fair_prob IS NULL could publish at all.
--
-- The two migrations were written against each other's drafts and the
-- gap survived both, because nothing executes this SQL: no Supabase
-- project has ever been provisioned. tests/unit/store/test_sql_invariants
-- .py::test_publish_run_writes_every_picks_column now asserts the INSERT
-- list covers every picks column, which is the general form of this bug —
-- fn_publish_run is the only writer of picks (§2.4), so a column it
-- cannot write is a column that can never be set.
--
-- 007 is left exactly as applied (migrations are additive); this
-- redefines the function. Same signature, so the grants in
-- db/policies/004_wave2_read_surface.sql still attach to it.
--
-- devig_method is deliberately NOT defaulted from markets.devig_method
-- when the caller omits it. markets.devig_method is the CONFIGURED
-- method; picks.devig_method records the method that ACTUALLY produced
-- this row's number (003's column comment) — the whole reason the column
-- exists is that picks is append-only and cannot be back-corrected if
-- the configured default later changes. Filling it in from configuration
-- would record a provenance nobody verified, which is worse than the
-- CHECK violation a caller gets for staying silent.

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
        raw_model_prob, model_prob, market_fair_prob, devig_method, market_odds_american, book,
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
        NULLIF(r ->> 'devig_method', ''),
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
