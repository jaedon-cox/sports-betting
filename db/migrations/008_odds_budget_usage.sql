-- Odds-budget usage ledger (§2.5): The Odds API free tier is 500
-- credits/month, and each GitHub Actions job runs on a fresh filesystem
-- — there's nowhere durable for `odds/budget.py` to keep a local
-- counter across the ~6 daily cron invocations that spend credits.
-- This table is that durable counter. Insert-only: a job records what it
-- spent right after the call succeeds; nothing ever edits a past spend.
--
-- Not in the doc's original table sketch (§3.2) — added on ingest's
-- request once they hit the actual "how does state survive an ephemeral
-- runner" problem building odds/budget.py. Squarely the same kind of
-- object as pipeline_runs: pipeline ops metadata, not a decision-bearing
-- value, so no append-only guard trigger is needed for correctness, but
-- it's kept insert-only anyway since a usage ledger that could be edited
-- after the fact isn't trustworthy as an audit trail either.

CREATE TABLE odds_budget_usage (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The Odds API's own monthly reset cycle, e.g. '2026-08' (UTC) — not
    -- necessarily the ET slate month, so this is a plain caller-supplied
    -- key rather than a DATE truncation computed here.
    month_key      TEXT NOT NULL,
    credits        INTEGER NOT NULL CHECK (credits > 0),
    endpoint       TEXT NOT NULL,
    called_at_utc  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_odds_budget_usage_month ON odds_budget_usage (month_key);

CREATE TRIGGER trg_odds_budget_usage_no_update
    BEFORE UPDATE ON odds_budget_usage FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();
CREATE TRIGGER trg_odds_budget_usage_no_delete
    BEFORE DELETE ON odds_budget_usage FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation();

-- One RPC for the one read `odds/budget.py` actually needs (headroom
-- check before a priced call) — keeps src/sbm/store/client.py from
-- needing a general-purpose query builder for a single SUM.
CREATE OR REPLACE FUNCTION fn_odds_budget_month_total(p_month_key TEXT) RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(SUM(credits), 0)::INTEGER FROM odds_budget_usage WHERE month_key = p_month_key;
$$;
