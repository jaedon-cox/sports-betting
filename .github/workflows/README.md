# workflows — the autonomous pipeline

Eight scheduled jobs (backend doc §2.4), one workflow each, all of them a single
`python -m sbm.jobs <letter>`. The job code is `src/sbm/jobs/`; these files are
only cron, secrets and the DST pre-check.

**Every workflow triggers on `schedule` and `workflow_dispatch` only — never
`pull_request`.** That is what closes the fork-PR secret-leak vector for the
Odds API and service-role keys, and it keeps the edge logic out of a public run
log (§2.4). Adding a `push:` or `pull_request:` trigger to any file here undoes
both.

## Secrets an operator must set

**No Supabase project has ever been provisioned.** Every name below refers to
something that does not exist yet; the jobs are written against it and will fail
with a named error until it does.

Repository **Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Used by | What it is |
|---|---|---|
| `SUPABASE_URL` | all | `https://<ref>.supabase.co`. `PostgrestClient` appends `/rest/v1`. |
| `SUPABASE_SERVICE_ROLE_KEY` | all | Service-role key. Bypasses RLS (§5) and is the only key granted EXECUTE on the pipeline's Postgres functions (`db/policies/004`). Never expose it to Edge Functions or client code. |
| `ODDS_API_KEY` | A, E | The Odds API free-tier key. |
| `REVALIDATE_SECRET` | A, D, E, F | Shared with the Vercel deployment; sent in the `x-revalidate-secret` header only. Must match the frontend's env var exactly or every purge 401s. |

Repository **Variables** (same page → Variables — these are not secret and are
visible in run logs):

| Variable | Used by | Default if unset |
|---|---|---|
| `SITE_URL` | A, D, E, F | none — the job raises `MissingSecret`. `https://<app>.vercel.app`, no trailing path. |
| `SBM_EDGE_THRESHOLD` | C, D, G | `0.0` — recommend any strictly positive edge. **No doc gives this number**; see `config.py`. |
| `SBM_N_DRAWS` | C, D, G | `100000` (§2.2) |
| `SBM_DAILY_ODDS_CREDITS` | E | `15` — 1 open snapshot + 4 closing sweeps (§2.5) |

An unset Actions variable interpolates to the empty string rather than being
dropped, which is why `JobConfig.from_env` treats empty as absent — a job must
never fail on a default.

`GITHUB_SHA` and `GITHUB_RUN_ID` are supplied by Actions and need no setup;
`GITHUB_SHA` is the canonical `model_versions.git_sha`.

## Schedule

Cron is UTC with no timezone field. Every job whose cadence is an ET *instant*
(A, C, D, F) is scheduled twice — the UTC time for that hour under EDT and under
EST — and a pre-check step calls `sbm.jobs.clock.is_intended_run` before any
dependency is installed, so the wrong trigger exits in seconds. GitHub bills
whole-minute increments **per invocation** (§2.2), so where that check happens
is a budget decision, not a style one. `workflow_dispatch` always bypasses the
guard: a manual re-run is deliberate, usually at the "wrong" hour on purpose.

| Job | ET target | UTC crons | Guard |
|---|---|---|---|
| A daily pull | 08:00 | `0 12`, `0 13` (Mar–Nov) | `is_intended_run(…, 8)` |
| B intraday | 10:00–22:00 hourly | `0 0-3,14-23` (Mar–Nov) | `is_within_et_hours(…, 10, 22)` |
| C pass A | 16:00 | `0 20`, `0 21` (Mar–Nov) | `is_intended_run(…, 16)` |
| D pass B | 18:15 | `15 22`, `15 23` (Mar–Nov) | `is_intended_run(…, 18, 15)` |
| E closing lines | 6 cluster times | see the file (Mar–Nov) + 3 November-only EST hedges | none needed — the window test compares UTC instants |
| F settlement | 04:00 | `0 8`, `0 9` (Mar–Nov) | `is_intended_run(…, 4)` |
| G backtest | Mondays | `0 15 * * 1` | none — the hour is not load-bearing |
| H heartbeat | Sundays | `0 15 * * 0`, **year-round** | none |
| I statcast | 05:00 ET-ish | `0 9 * * *` | none — the window is a date range, so DST is irrelevant |

Months 3–11 keep the seasonal jobs from billing anything in the offseason. Job H
is the only one without a month filter, which is its entire purpose: the
offseason has no daily writes, and a 7-day idle auto-pause would need a manual
resume before the season's first pull (§2.4, §7 item 8).

Job E's `20 1` and `50 1` crons are the *previous* ET evening; the month filter
applies to the UTC date, so the last evening of October still runs (Nov 1 UTC).

## Two budgets, both real constraints

**Actions minutes** — ~2000/month on a private repo (§2.2). Rough steady-state:

| Job | Invocations/day | Billed min each | Per month |
|---|---|---|---|
| A | 1 real + 1 guarded | 3 + 1 | ~120 |
| B | ~14 | 1 | ~420 |
| C | 1 real + 1 guarded | 3 + 1 | ~120 |
| D | 1 real + 1 guarded | 3 + 1 | ~120 |
| E | 6 (9 in November) | 2 | ~360 |
| F | 1 real + 1 guarded | 3 + 1 | ~120 |
| G | weekly | ~15 | ~65 |
| H | weekly | 1 | ~4 |
| I | 1 | ~4 | ~120 |

≈ **1450/month in season**, against the 2000 cap. Jobs B and H install `httpx`
alone rather than the scientific stack, which is what keeps B's ~420 invocations
at one billed minute each; `tests/unit/jobs/test_dependency_profile.py` fails the
build if an import ever makes that untrue.

**Odds API credits** — 500/month, the tightest constraint in the system (§2.5).
Job A's open snapshot costs 3 and is never paced; Job E's closing sweeps cost 3
each and go through `jobs/pacing.py`, which allows a cumulative `15 × day-of-month`
(465 by month end, leaving ~35 for doubleheaders and retries). A refused sweep is
the documented precision-for-budget tradeoff, not a failure. Jobs C and D price
against the *stored* open snapshot rather than buying their own — a third daily
call would be ~90 extra credits/month and put the system over the cap.

## Database functions these jobs require

All shipped by `db` and granted to `service_role` only:

| Function | Migration | Called by |
|---|---|---|
| `fn_publish_run` | 007, 013 | D (and C), via `store.publish_run` |
| `fn_latest_lines` | 012 | C, D |
| `fn_unsettled_picks` | 012 | F |
| `fn_settled_picks_for_date` | 014 | F |
| `fn_record_results` | 014 | F |
| `fn_refresh_rollups` | 011 | F |
| `fn_backtest_rows` | 015 | G |
| `fn_odds_budget_month_total` | 008 | every priced call, plus H |
| `fn_pitcher_game_form` | 018 | C, D (via `features/source/`) |
| `fn_bullpen_game_form` | 018 | C, D |
| `fn_team_batting_form` | 018 | C, D |
| `fn_injury_status_asof` | 018 | C, D |
| `fn_weather_asof` | 018 | C, D |

`src/sbm/jobs/rpc.py` is the only module naming them, so a rename upstream
changes one file.

## What is covered by tests, and what cannot be

`python3 -m pytest tests/unit/jobs tests/unit/store` runs the whole pipeline
suite with no network and no Supabase project. Every job module A-H has
coverage; the fakes are in `tests/unit/jobs/fakes.py`.

What the suite actually pins is the *composition* — which of the four side
effects (slate status, raw archive, ISR purge, atomic publish) each job performs
on each branch, and every documented skip rule. Those are the parts a refactor
breaks silently, because a missing call looks exactly like a working job: an
off-day that spends no Odds API credits, a failed Pass B that records `failed`
and does **not** purge the cache, a doubleheader that pulls each roster once, a
venue with no coordinates that writes no row rather than a row of nulls.

Three things are deliberately not covered, and no amount of unit testing can
cover them:

1. **Cron correctness.** `clock.py`'s guards are tested against ET instants, but
   whether a given UTC cron actually fires at that instant is GitHub's
   scheduler. The month filters and the November-only Job E hedges are unverified
   until a live season.
2. **Every PostgREST call shape.** `FakeClient` records the table, the rows and
   the `on_conflict` key, and `tests/unit/store/test_sql_invariants.py` reads the
   migrations, but nothing here has ever spoken to real PostgREST — no Supabase
   project has been provisioned.
3. **Whether the feature store has data in it.** `PostgrestSnapshotSource` is
   unit-tested against fake RPC results, and the rate math was validated against
   three months of live Statcast (xFIP median 3.82, CSW% 26.6%, GB% 42.4%, an
   average matchup projecting 9.25 total runs). What no test can tell you is
   whether Job I has actually populated the tables for the slate being priced —
   an empty store produces league-average features and a plausible-looking board.
   Check `SELECT count(*) FROM pitcher_game_stats` before trusting a pick.

## Operating notes

- **A red run is the alert.** §2.4's failure handling is GitHub's built-in
  workflow-failure email plus a `pipeline_runs` row at start and end of every
  invocation; there is no separate alerting path. A guarded-out DST duplicate
  writes no row, so `pipeline_runs` counts stay meaningful.
- **Re-running is safe.** `fn_publish_run` no-ops against an already-successful
  (version, date, pass); settlement is keyed on the absence of a
  `pick_settlements` row; `games`/`teams` upsert. The one thing a re-run costs is
  Odds API credits, so Jobs A and E should be re-run deliberately.
- **`SlateIntegrityError` means the schedule join is broken**, not that the feed
  ran ahead of us. It fires only on `NOT_INGESTED` — a gamePk the odds feed knows
  and `games` does not. Doubleheaders and off-slate games are counted separately
  and never alert.
- **Job I must have run before C or D can price anything.** The feature store
  it fills (`pitcher_game_stats`, `team_batting_game_stats`) is where every
  model input comes from; with it empty, every feature is NaN and
  `model/columns.py` substitutes league averages for all thirty clubs — so C
  and D succeed, publish, and produce a board of picks with no information in
  it. That failure is silent, which makes it the most dangerous state in the
  system. **Backfill a season first**: dispatch Job I with `from`/`to` set.
- **Only Job I installs the `mlb` extra.** C and D read the stat tables out of
  Postgres and never touch Statcast, so `pip install -e .` is right for them.
  `tests/unit/jobs/test_dependency_profile.py` asserts the workflows and the
  import closure agree, in both directions.
- **The Odds API region param is still [OPEN]** (§7 item 4). `theoddsapi.py`
  fails loud if a response carries other books but not Pinnacle; verify against a
  live key before trusting any CLV number.
