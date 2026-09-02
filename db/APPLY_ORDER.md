# Applying `db/` — read this before provisioning

No Supabase project has ever been provisioned, so nothing in this directory has
been executed. This file is the apply order. It is not documentation of a
convention — it is the only record of the order, and applying the directory any
other way fails.

**In particular, `db/views/` cannot be applied alphabetically.** `mv_clv_trend`,
`mv_roi_curve` and `record_breakdown` all depend on `record_summary.sql`, which
sorts after all three. A naive `for f in db/views/*.sql` aborts with
`relation "record_summary" does not exist`.

`tests/unit/store/test_sql_invariants.py` asserts that every `.sql` file in
`db/` appears in the manifest below exactly once, and that the manifest respects
the dependency edges that are not visible from the filenames. Add a file without
adding it here and the build fails — which is the point, because a manifest
nobody maintains reproduces the alphabetical-order bug it exists to prevent.

## The manifest

Apply top to bottom. Phase order (`migrations/` → `views/` → `policies/`) is
load-bearing, not stylistic: `policies/001` does
`REVOKE ALL ON ALL TABLES IN SCHEMA public`, which only covers the views and
matviews if they already exist.

```text
db/migrations/001_reference_and_versioning.sql
db/migrations/002_games_and_results.sql
db/migrations/003_picks.sql
db/migrations/004_line_history_and_settlement.sql
db/migrations/005_point_in_time_snapshots.sql
db/migrations/006_users_and_auth.sql
db/migrations/007_atomic_publish.sql
db/migrations/008_odds_budget_usage.sql
db/migrations/009_slate_status.sql
db/migrations/010_drop_bankroll_usd.sql
db/migrations/011_rollup_refresh.sql
db/migrations/012_pipeline_reads.sql
db/migrations/013_publish_run_devig_method.sql
db/migrations/014_settlement_rpcs.sql
db/migrations/015_backtest_rows.sql
db/migrations/016_settlement_clv_provenance.sql
db/migrations/017_player_game_stats.sql
db/migrations/018_feature_reads.sql
db/views/record_summary.sql
db/views/record_breakdown.sql
db/views/mv_clv_trend.sql
db/views/mv_roi_curve.sql
db/views/calibration_buckets.sql
db/views/v_todays_picks.sql
db/views/v_pick_archive.sql
db/views/v_pick_clv_live.sql
db/policies/001_enable_rls.sql
db/policies/002_authenticated_read_grants.sql
db/policies/003_user_owned_rls.sql
db/policies/004_wave2_read_surface.sql
db/policies/005_feature_reads.sql
```

Within `migrations/`, numeric order is the dependency order and there is nothing
subtle in it. Within `views/`, only `record_summary.sql` being first is
load-bearing; the five files after `mv_roi_curve.sql` are mutually independent
and their relative order is free. Within `policies/`, numeric order is required.

## What a flat list cannot express

The lead asked for these to be named rather than flattened into a sequence that
looks complete and isn't. There are five.

### 1. `record_breakdown.sql` depends on a *function*, not on `record_summary`

It reads `fn_american_payout_multiplier`, which is defined inside
`record_summary.sql` rather than in a migration. So the dependency is on that
**file**, not on the `record_summary` matview — `record_breakdown` never selects
from it. Reading the object graph alone would miss this edge entirely, which is
why the guard test hard-codes it.

The single definition is deliberate: two copies of the payout math is exactly
the kind of drift that produces two different ROI numbers.

### 2. `migrations/011` names relations that `views/` has not created yet

`fn_refresh_rollups` refreshes four matviews, all created later in `views/`.
This is a dependency pointing *backwards* against the apply order, and it is
safe only because PL/pgSQL defers name resolution of embedded statements to
first execution. A `LANGUAGE sql` function in its place would fail at
`CREATE FUNCTION` time.

**Do not "simplify" 011 to `LANGUAGE sql`, and do not move it after `views/` to
"fix" the ordering** — it is a migration and belongs in the numbered sequence.
The file says both things in its own header.

### 3. `policies/004` must be re-run after *any* later DDL — an event, not a position

Two independent reasons, both of which fire on a change made long after the
initial provision:

- **The re-grant hazard.** `CREATE OR REPLACE FUNCTION` preserves an ACL, but a
  function ever dropped and recreated picks up Supabase's
  `ALTER DEFAULT PRIVILEGES` on schema `public` and silently regains `EXECUTE`
  for `anon` and `authenticated`. `policies/004` is where that is revoked for all
  six RPCs, so it has to run again.
- **The PostgREST schema cache.** `NOTIFY pgrst, 'reload schema'` is the last
  statement in `policies/004`. Until it fires, a newly created relation answers
  `404 PGRST205` to a perfectly authorised request — a failure that looks
  identical to a missing GRANT.

`policies/004` is written to be idempotent for this reason (its `CREATE POLICY`
is preceded by `DROP POLICY IF EXISTS`). **`policies/001`–`003` are not** — their
bare `CREATE POLICY` statements abort on a second run. So the rule is
specifically "re-run `004`", not "re-run `policies/`".

### 4. Nothing here is idempotent except `policies/004`

`migrations/` and `views/` both use bare `CREATE TABLE` / `CREATE VIEW` /
`CREATE MATERIALIZED VIEW`. They are once-only against a given database. There is
no migration-state table and no runner — applying twice is an error, not a no-op,
and `010_drop_bankroll_usd.sql` in particular fails the second time with
`column "bankroll_usd" of relation "user_settings" does not exist`.

If a migration runner is adopted later, this manifest is the seed order.

### 5. The order is necessary, not sufficient

Applying in this order is what makes the SQL *parse*. Two things it cannot give
you, both of which need the live project:

- `public` must be in the project's PostgREST exposed-schemas list, or the
  matviews are unreachable regardless of any GRANT here. That is a dashboard
  setting.
- `service_role` must exist when `policies/004` runs, or its `GRANT EXECUTE`
  statements error and the `NOTIFY` below them never fires. Supabase creates the
  role at project bootstrap.

## Not addressed here

A numbered-prefix scheme across `views/` would encode the order in the filenames
and make this file unnecessary. It was deliberately not done: `src/sbm/jobs/` and
`web/README.md` both reference these filenames, and `pipeline` was mid-flight.
The rename is the better long-term fix and is safe to do once wave 2 lands.

