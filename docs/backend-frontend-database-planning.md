# Backend / Frontend / Database Planning — MLB +EV Picks Web App

> Compiled by the **planning-team** lead from four Sonnet teammates (Backend, Frontend, Database, Critic)
> after a full round-trip exchange (draft → cross-team contract negotiation → Critic review → revision).
> Companion to [`model-and-feature-planning.md`](./model-and-feature-planning.md), which specifies the model itself.
> Date: 2026-06-30.

---

## 0. Scope & goal

Take the existing MLB +EV model — a Negative-Binomial Monte-Carlo run-distribution engine producing daily
picks across three markets (**moneyline, run totals, run-line ±1.5**), optimizing for **calibration and
Closing Line Value (CLV)** — and wrap it in a system that:

1. **Gathers** the necessary data with strict point-in-time / no-leakage discipline (doc §5).
2. **Runs** the daily pipeline and periodic backtests efficiently enough to produce value.
3. **Serves** daily picks to a web app where users **log in and view the day's picks**.
4. **Tracks** the model's record over time (CLV, calibration, ROI) for users to view.

Under two hard constraints: **runs autonomously** and **costs $0** (free tiers only).

### 0.1 How this document was produced

Four teammates ran a structured exchange:
- **Backend**, **Frontend**, and **Database** each drafted their layer, negotiated the shared API/schema
  contract directly with one another, sent drafts to the **Critic**, and revised on the critique.
- The **Critic** reviewed all three, sent itemized critiques back, and produced the consolidated review in §6.

This file is the lead's synthesis. Items marked **[OPEN]** are unresolved and need a human decision (see §7).

---

## 1. Architecture at a glance

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  GitHub Actions (cron)  ──  ALL compute, orchestration, scheduling │
   │  data pull → feature build → NB Monte-Carlo sim → edge/CLV → write │
   └───────────────┬──────────────────────────────────────────────────┘
                   │ writes via service-role key (bypasses RLS)
                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Supabase (Postgres + Auth + PostgREST + RLS + Edge Functions)     │
   │  append-only picks/snapshots · materialized-view rollups · auth    │
   └───────────────┬──────────────────────────────────────────────────┘
                   │ authenticated, RLS-scoped reads (PostgREST / supabase-js)
                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Next.js 14 (App Router) on Vercel Hobby                           │
   │  Server Components query Supabase directly — no hand-rolled REST    │
   └──────────────────────────────────────────────────────────────────┘
```

**The single most important architectural decision:** there is **no hand-rolled REST API**. All three
teammates independently converged on Supabase, so Next.js Server Components query Postgres directly
(RLS-enforced), and Backend's only serving-side responsibility is (a) the autonomous pipeline that writes
data and (b) firing a cache-revalidation webhook when a run completes. This is cheaper (no per-invocation
serverless cost for reads with no business logic) and simpler (auth enforced once, at the DB layer).

### 1.1 The $0 stack

| Service | Role | Free-tier limit | Where it bites |
|---|---|---|---|
| **GitHub Actions** | Cron + all compute (pipeline, sim, backtest) | 2000 min/mo (private repo); using ~1050/mo in-season | Bills whole-minute increments per invocation — polling frequency, not runtime, drives cost |
| **Supabase** | Postgres + Auth + PostgREST + Edge Functions | 500 MB DB, 5 GB egress/mo, 50k MAU, 500k edge calls/mo | Auto-pauses after 7 days fully idle; no auto-backups |
| **Vercel Hobby** | Next.js hosting | Generous for this traffic; non-commercial ToS | Must stay non-commercial |
| **The Odds API** | Pinnacle odds (h2h/totals/spreads) | **500 req/mo** — the tightest constraint; ~450 used | Caps line-movement granularity to open+close |
| **MLB StatsAPI** | Schedule, rosters/IL, scores, results | Unofficial, self-throttle ≤1 req/s | No SLA; IL feed ≈ public-simultaneous (see §7) |
| **pybaseball / Statcast** | SIERA, wRC+, xwOBA, CSW%, park, OAA | Scraping-based, no formal cap | Fragile to upstream site changes |
| **Open-Meteo** | Weather forecast + historical archive | ~10k calls/day, no key | Use forecast, never observed actuals (doc §3.7) |

---

## 2. Backend plan

### 2.1 Data gathering

| Source | What | Cadence |
|---|---|---|
| MLB StatsAPI | schedule, probable pitchers, roster/IL, live scores, final results | schedule 1×/day (8am ET); roster/IL hourly 10am ET→first pitch; final scores nightly (Job F) |
| pybaseball (FanGraphs/Savant/BBRef) | SIERA, xFIP, wRC+, xwOBA, CSW%, park factors, OAA/DRS | 1×/day, prior-day batch, disk-cached |
| Baseball Savant Statcast | pitch-level data for CSW%/Stuff+ | nightly batch, prior-day range |
| Open-Meteo | pre-game wind/temp/humidity **forecast** (+ archive for backtest) | 1×/day/game, refreshed a few hours pre-lock |
| The Odds API | Pinnacle odds, `bookmakers=pinnacle` | see §2.5 — **2 snapshots/game** (open + close) |
| Historical Pinnacle closing lines | backtest only | **[OPEN]** — no free source identified |

**Point-in-time / leakage design (doc §5):** every ingested blob lands in an append-only
`raw_snapshots(payload jsonb, pulled_at_utc)` table — never mutated. The feature-builder takes an
`as_of` timestamp and the **same function serves both live production and backtest reconstruction**, so
they cannot silently diverge into different leakage regimes. This fixes the *mechanism* but does **not**
prove StatsAPI's roster/IL timestamps reflect true public-availability time — that needs an empirical
spot-check before any backtest CLV is trusted (see §7).

### 2.2 Model execution & backtesting

- **Feature build:** pandas/numpy point-in-time joins against `raw_snapshots` at a given `as_of`.
- **NB Monte Carlo:** numpy-vectorized, N=100k draws/game/side, matchup-varying α (doc A6). Full ~15-game
  slate runs in well under a minute.
- **Backtesting:** thousands of games, still vectorized — a few minutes for a multi-season run. Runs via
  `workflow_dispatch` or weekly schedule, **not on every push**, to conserve Actions minutes.
- **GBT ensemble** (only if it clears the pre-specified Brier threshold, doc §10.6): retrained weekly.
- **Actions budget (corrected):** ~1050 min/mo in-season against the 2000/mo private-repo cap (~47%
  headroom). GitHub bills **whole-minute increments per invocation**, so *polling frequency* — not job
  runtime — is the real cost driver: the original continuous 5-min closing-line checker (~13 hrs/day)
  alone would have burned ~150 billed min/day and blown the monthly cap in about a week. See Job E's
  redesign below.

### 2.3 Serving the frontend

Backend's serving surface reduces to three things:
1. **The autonomous pipeline** — writes via the Supabase service-role key; invisible to the frontend
   beyond the tables/views it produces.
2. **On-demand cache revalidation** — a `curl` step at the end of each successful run (or a Supabase DB
   webhook) hits Frontend's Next.js revalidate endpoint. No polling, no websockets — CLV settles at the
   T-5min close, so nothing needs to be live.
3. **Admin allowlist management** — **not needed.** Uses Supabase's `auth.admin.inviteUserByEmail()`
   with self-serve signup disabled; no custom allowlist table.

Data surfaces Frontend reads directly (see §4 and §5.5 for the reconciled view names).

### 2.4 Autonomous scheduling (GitHub Actions cron, UTC — watch DST)

| Job | Timing | Does |
|---|---|---|
| A. Daily data pull | ~8am ET | schedule, probables, pybaseball/Statcast batch, park factors, weather forecast, **opening odds** |
| B. Intraday refresh | **hourly**, 10am ET→first pitch | roster/IL, lineup confirmations |
| C. Model run — Pass A | ~3h pre-game | features on **projected** lineups → research/early-signal pick (not official) |
| D. Model run — Pass B | ~T-45min, after confirmed lineups | re-run with confirmed-lineup delta → **official pick** for CLV |
| E. Closing-line capture | **~6 scheduled cron triggers/day** at known start-time cluster windows | each does one cheap schedule check, sweeps any in-window game, exits immediately (no continuous polling) |
| F. Settlement | nightly, post-games | final scores → outcome + CLV per pick; refresh all rollup matviews |
| G. Backtest | on-demand / weekly | full historical re-run |
| H. Heartbeat | **weekly, year-round** | trivial `SELECT 1` + a `pipeline_runs` row — keeps Supabase alive through the offseason (see below) |

- Every `model_run` is a **new row, never a mutation**; `picks` is append-only. `today_picks` selects the
  latest official run per (game, market). Both passes retained for research.
- **Secrets & CI security:** Odds API key + Supabase service-role key live in GitHub Actions Secrets.
  The repo is **private**, and workflows trigger only on `schedule`/`workflow_dispatch` — **never
  `pull_request`** — closing the fork-PR secret-leak vector and keeping the model's edge logic
  non-public (a competitive concern too). Private-repo Actions minutes ≈ **1050/mo in-season vs. the
  2000/mo cap** (see §2.2). The service-role key is scoped only to the write-jobs that need it — never
  exposed to Edge Functions or client code.
- **Failure handling:** GitHub's built-in workflow-failure email + a `pipeline_runs` table row at
  start/end of every job (queryable health; lets the frontend show "picks pending" not an empty state).
- **`model_runs` granularity:** **one row per `(run_date, pass_type)`** covering the whole day's slate
  (not per-game), so atomic-publish is a single-row status check. `picks` FK to it; `UNIQUE(game_id,
  market, model_run_id)` still gives one pick per game/market/run.
- **Idempotency:** natural key `(model_version, run_date, pass_type)`; retry logic no-ops if a
  `status='success'` row already exists for that key, and a **partial unique index (`WHERE
  status='success'`)** makes duplicate successful runs structurally impossible. (Games upsert on `gamePk`.)
  Backend's original "upsert on `(game_id, market, model_version)`" language was retracted.
- **Atomic publish:** the day's `model_runs` row starts `status='running'`, writes the *full* slate's
  picks, and flips to `status='success'` **only as its last step**, inside one transaction. `today_picks`
  filters strictly to the latest run where `status='success'`, so a job that dies at game 8 of 15 leaves
  that run's rows invisible and the frontend keeps showing the last known-good complete slate. The
  Supabase revalidation webhook is scoped to exactly that transition
  (`WHEN NEW.status='success' AND OLD.status IS DISTINCT FROM 'success'`), not a generic fire-on-insert.
- **Offseason dormancy:** the "daily writes keep Supabase alive" assumption only holds in-season. The MLB
  offseason (~Nov–Feb) has no games and no daily pipeline, which would trigger repeated 7-day auto-pauses
  — hence job H, a weekly heartbeat that runs year-round independent of the season schedule.

### 2.5 The odds budget — the system's tightest constraint

The Odds API free tier is **500 requests/month**; each call costs `markets × regions` credits
(3 markets × 1 region = 3 credits). MLB start times stagger across the day (day games, ~7pm wave,
~9–10pm West-coast wave), so a fixed "poll N times/day" timer misses each game's actual close. The
budget-verified cadence is **1 open snapshot/day** (all games in one call) **+ up to 4 closing-window
sweeps/day** fired from **~6 scheduled cron triggers** positioned at known MLB start-time cluster windows
(each does one cheap schedule check and sweeps any in-window game — no continuous 5-min polling, which
would blow the Actions-minute budget; see §2.2). Each game gets ~2 snapshots (open, close):
**15 credits/day × 30 ≈ 450/month against the 500 cap**, leaving ~50/month for doubleheaders and retries.
On a rare 5+-cluster night the job merges the two closest clusters and widens tolerance to T-15→T-2 for
one — a documented precision-for-budget tradeoff. This directly bounds the doc's §11 line-movement
question: **only a coarse open→close gap is buildable on $0, not continuous steam/velocity detection.**

---

## 3. Database plan (Supabase Postgres)

### 3.1 Guiding invariant: insert-only everywhere

`picks`, `line_snapshots`, `lineup_snapshots`, `injury_snapshots`, `weather_snapshots`, `results`,
`pick_settlements`, and `raw_snapshots` **never** receive an UPDATE or DELETE in normal operation. DB
triggers enforce this on `picks` at minimum. **Corrections are new rows (a new `model_run`), never
mutations** — this is what makes the model's track record trustworthy and satisfies the doc's §5
point-in-time integrity requirement. The deliberate exceptions are `pipeline_runs` (job status
transitions), `user_settings` (user-owned state), and a **single** legitimate `model_runs` UPDATE — the
`running → success` status flip (status metadata isn't a decision-bearing value, so it doesn't touch the
leakage-prevention principle). `picks` and `line_snapshots` remain fully insert-only with no exceptions.

### 3.2 Schema sketch (key tables)

```sql
-- Reference / versioning
model_versions (id PK, git_sha TEXT UNIQUE NOT NULL,  -- canonical version key
                semver_label, config_hash, is_active, created_at)
model_runs (id PK, model_version_id FK, run_date DATE,
            pass_type TEXT CHECK IN ('projected','confirmed'),  -- Run A vs official Run B
            status TEXT CHECK IN ('running','success','failed','partial'), github_run_id)
teams (id PK, code UNIQUE, name, league, division)

-- Games & results
games (id PK, external_game_id TEXT UNIQUE,  -- MLB gamePk, upsert key
       game_date DATE,  -- ET slate-date, start_time_utc, home/away_team_id FK, park_name,
       status CHECK IN ('scheduled','in_progress','final','postponed','cancelled'))
results (game_id PK/FK, home_runs, away_runs, final_status, settled_at)  -- insert-once at final

-- Picks: core append-only fact table (favored side only — NB joint dist makes sides complementary)
picks (id PK, model_run_id FK, game_id FK, game_date DATE,  -- denormalized for index-only archive
       market CHECK IN ('moneyline','total','run_line'),
       side CHECK IN ('home','away','over','under'),  -- + CHECK total↔over/under
       line,                          -- spread/total number (e.g. -1.5, 8.5)
       raw_model_prob NUMERIC(6,5),   -- pre-calibration NB output (drift monitoring)
       model_prob NUMERIC(6,5),       -- post isotonic/Platt (A5) — drives edge/Kelly
       market_fair_prob NUMERIC(6,5), -- de-vigged Pinnacle at pick time
       market_odds_american, book TEXT DEFAULT 'pinnacle', edge_pct,
       recommended BOOL,              -- false rows kept → CLV on ALL evaluated games (doc §7)
       kelly_stake_fraction NUMERIC(6,4),  -- % of bankroll ONLY, never a $ amount
       pick_locked_at, created_at,
       UNIQUE (game_id, market, model_run_id))
-- Trigger: RAISE EXCEPTION on UPDATE/DELETE.

-- Line history & settlement (insert-only)
line_snapshots (id PK, game_id FK, market, side, price_american, implied_prob_devigged,
                captured_at_utc, source DEFAULT 'pinnacle', is_closing BOOL)  -- flags T-5min close
pick_settlements (pick_id PK/FK, outcome CHECK IN ('win','loss','push','void'),
                  clv_pct, closing_prob, bet_prob, settled_at)  -- insert-once, post-game

-- Point-in-time input snapshots (Critic must-fix: capture inputs, not just outputs)
lineup_snapshots  (id PK, game_id FK, team_id FK, batting_order JSONB, is_confirmed BOOL, captured_at_utc)
injury_snapshots  (id PK, player_id, team_id FK, status, note, captured_at_utc)
weather_snapshots (id PK, game_id FK, temp_f, wind_mph, wind_dir_deg, precip_pct,
                   is_forecast BOOL,  -- structurally enforces doc §3.7 forecast-only in backtests
                   captured_at_utc)
raw_snapshots (id PK, source, entity_type, entity_id, payload JSONB, pulled_at_utc)  -- full-fidelity archive
pipeline_runs (run_id PK, job_name, status, started_at, finished_at, error_message)  -- ops health

-- Users / auth (see §3.5)
profiles       (id PK/FK → auth.users.id, display_name, role, created_at)
user_settings  (user_id PK/FK, bankroll_usd, notify_email, created_at, updated_at)
user_saved_picks (user_id FK, pick_id FK, saved_at, PK(user_id, pick_id))  -- deferred/optional
```

Snapshot tables are the **fast queryable extraction layer**; `raw_snapshots` is the full-fidelity archive
underneath. "As-of-t" joins use `WHERE captured_at_utc <= pick_locked_at ORDER BY captured_at_utc DESC LIMIT 1`.

### 3.3 Record-tracking design (nothing aggregates raw `picks` at request time)

All of the below are written/refreshed by Backend's nightly settlement job (Job F).

- **`record_summary`** (matview, grain `rollup_date × market[NULL = blended]`) — `n_evaluated`,
  `n_recommended`, wins/losses/pushes, `units_staked`, `units_won`, `roi_pct`, `avg_clv_pct`,
  `clv_positive_rate`, `avg_edge_pct`. Frontend **sums over the daily grain** for any window (sum, not
  average-of-averages, so it composes correctly). Full nightly recompute is idempotent.
- **`mv_clv_trend`, `mv_roi_curve`** (matviews) — running-sum window functions over `record_summary`,
  feeding the cumulative CLV/ROI charts directly. (Note: `REFRESH ... CONCURRENTLY` needs a unique index
  on the matview itself.)
- **`calibration_buckets`** — a **physical table, not a matview** (needs versioning a REFRESH can't give).
  A `REFRESH` would recompute *all* history under any new bucketing method, silently changing past
  numbers; instead the nightly job does an explicit `INSERT/UPSERT ON CONFLICT (rollup_date, market,
  predicted_bucket, method_version)`, so dashboards pinned to an old `method_version` stay numerically
  stable. v1: blended-only, 10 deciles via `width_bucket()`; per-market split is a non-breaking future add.
- **Read views:** `v_todays_picks`, `v_pick_archive` (keyset-paginated `(game_date DESC, id DESC)`,
  backed by composite index `picks(game_date DESC, market, recommended)`), `v_pick_clv_live`.
- **Optional (Backend's call):** `model_run_features(model_run_id, game_id, features JSONB, captured_at)`
  — the *exact* feature vector a run consumed (vs. snapshot tables, which capture what was *available*).
  Valuable for reproducibility/drift debugging; not mandated.

### 3.4 Why Supabase, and the free-tier math

Chosen over Neon (no native auth), Turso/D1 (SQLite — weaker for the window-function/matview-heavy rollup
design), and PlanetScale (dropped its free tier). Volume: ~32k `picks` rows/yr (2 passes × ~15 games ×
3 markets) — years of headroom in 500 MB. **The snapshot tables + `raw_snapshots` JSONB are the real
storage risk** → pruning policy in §3.6. Auto-pause after 7 idle days is a non-issue given daily writes,
**provided** `pipeline_runs` alerts catch a silent pipeline death before it compounds into a paused DB.

### 3.5 Auth storage & RLS (Critic must-fix folded in)

Auth fully delegated to **Supabase Auth** — invite-only via `auth.admin.inviteUserByEmail()` with
self-serve signup disabled; `auth.users` existence *is* the allowlist (no custom table). App-owned:
`profiles` (linkage + display) and `user_settings` (bankroll, prefs).

**RLS — explicit anon-deny:** SELECT policies on `picks`, `games`, all snapshot tables, and rollups are
scoped `TO authenticated` **only — never `TO public`/`anon`**. Because Supabase's anon key is not secret,
RLS is the only real gate: a logged-out visitor (even with a leaked anon key) sees nothing but the login
page. `profiles`/`user_settings`/`user_saved_picks` add an `auth.uid() = user_id` row filter on top. All
writes go through the service-role key from the pipeline, bypassing RLS — there is **no user-facing write
path** except a user editing their own `user_settings`.

**Bankroll immutability:** `picks.kelly_stake_fraction` (a %) is the **only** stake figure ever persisted.
No $ amount is stored anywhere, so changing bankroll never rewrites historical stakes — "$ stake" exists
only as a live `% × current bankroll` computation for *today's* picks. A future bankroll-tracking feature
would need its own `user_bet_log` with a `bankroll_usd_at_time` snapshot; deliberately not in v1.

### 3.6 Lifecycle

- **Retention:** indefinite for `picks`/`results`/`pick_settlements`/rollups (small; this *is* the track
  record). Snapshot storage is bounded by **scoping `raw_snapshots` to point-in-time-sensitive categories
  only** (lineups, injuries, odds, weather) and explicitly **excluding bulk pybaseball/Statcast pulls**,
  which carry no leakage risk and would otherwise dominate the 500 MB cap. Rough budget: **~65 MB/season**
  with that scoping. No proactive pruning; a **monthly size-check job** flags if the DB approaches
  350–400 MB, with Cloudflare R2 cold-archive or a multi-season drop as fallbacks.
- **Backups (hardened):** free tier has none. Nightly `pg_dump` via a scheduled Actions workflow
  (`schedule`/`workflow_dispatch` only, never `pull_request`), using a **dedicated read-only Postgres
  role** (separate from the write service-role key, to cap blast radius if the CI secret leaks) →
  **Cloudflare R2's free 10 GB**. A **monthly restore-into-scratch-DB job** with row-count sanity checks —
  a dump that exits 0 is not a validated backup. The snapshot tables are the priority backup target once
  they exist (non-regenerable, unlike games/scores which can be re-pulled from StatsAPI). Restore
  validation is **specified but not yet run**.

---

## 4. Frontend plan

### 4.1 Page inventory

1. **Login** — invite-only magic-link, no password, no self-serve signup. Email → "check your inbox" →
   click link → session.
2. **Today's Picks (home)** — per game: matchup, start time, park. Per market: side, line, quoted odds,
   `model_prob` vs. de-vigged `market_fair_prob`, `edge_pct`, Kelly stake %, confidence tier (derived
   client-side). Toggle **recommended-only vs. all-evaluated (defaults to all-evaluated**, matching the
   CLV-on-all spec), always visibly labeled. Summary strip (# picks, total exposure %, avg edge). Banner:
   **"picks generated at HH:MM ET."** Per-game status badge: *"line open"* (pre-close) or *"closed — CLV
   +X bps"* (post-close), since closing times stagger across the slate.
3. **Model Record** — CLV trend (daily, per-market + blended), calibration reliability diagram, ROI curve.
   **ROI is visually subordinate** to CLV/calibration (smaller module + explicit "noise under ~2000 bets"
   disclaimer), mirroring the doc's own framing. **N shown next to every aggregate stat.** Breakdowns by
   market / favorite-dog / edge-bucket; time-range selector (7d/30d/season/all-time).
4. **Pick Detail** — full context + an **open → close comparison** (two values + CLV delta), *not* a
   chart — with only 2 odds points, a chart would imply false granularity. Result + realized CLV.
5. **Historical Picks / Archive** — filterable, keyset-paginated log (date range, market, result, scope).
6. **Account / Settings** — bankroll $ input (drives only *today's* $ display, never rewrites history),
   notification prefs, sign out. Responsible-gambling disclaimer in the footer.
7. **Empty/error states** — off-day (no games) vs. "today's picks pending" (pipeline running) — distinct.

### 4.2 Aesthetic — "night game" scoreboard/ledger

Deliberately not the generic AI defaults. Baseball's own visual vernacular (manually-operated split-flap
scoreboards, box scores) crossed with fintech numeric precision — the app's whole job is *"should I trust
these numbers,"* so restraint governs everything except one signature moment.

| Token | Hex | Use |
|---|---|---|
| Ink | `#0E1A17` | Background — warm deep pine-navy, not neutral black |
| Surface | `#16241F` | Cards/panels |
| Chalk | `#F2EEE3` | Primary text — warm off-white |
| Floodlight | `#E8A33D` | Accent/CTA — stadium-light gold |
| Turf | `#4E9F76` | Positive signal (win / +CLV / cover) |
| Clay | `#C15B3E` | Negative signal (loss / −CLV) |

**Type:** display = Big Shoulders Display (condensed athletic-signage, headlines only); body = Public Sans;
data = **IBM Plex Mono** for every odds/edge/CLV/stake figure, tabular-aligned. **Layout:** box-score grid,
right-aligned tabular numerals, hairlines as detail. Mobile: rows collapse to cards. **Signature:** headline
numbers (today's exposure %, season record) use a **split-flap "flip-digit" animation** on load — a direct
ballpark-scoreboard reference, CSS/JS only, respects `prefers-reduced-motion`.

### 4.3 Stack + hosting ($0)

- **Next.js 14 (App Router) + TypeScript + Tailwind** on **Vercel Hobby** (non-commercial use fits ToS).
- **No custom REST server for reads** — Server Components query Supabase directly (RLS-scoped),
  revalidated via Backend's on-demand webhook (no polling / websockets).
- **Charts:** `visx` (unstyled primitives, matches the bespoke aesthetic), marked `"use client"`.
- **Fonts:** Google Fonts self-hosted via `next/font` (no external requests, no layout shift).

### 4.4 Auth UX

Invite-only magic-link. No passwords, no OAuth, no self-serve signup, **no allowlist table to build** —
admin invites an email via `inviteUserByEmail()` (creates the user + sends the link in one call);
self-serve signup disabled in Supabase Auth settings. Protected routes redirect unauthenticated visitors
to `/login?next=…`, checked server-side (no flash of protected content).

### 4.5 Data per view

| View | Source | Read path |
|---|---|---|
| Today's Picks | `v_todays_picks` (flat, grouped client-side by `game_id`) + `model_runs` publish time | Direct Supabase (Server Component), RLS-scoped |
| Model Record | `record_summary` / `mv_clv_trend` / `mv_roi_curve` + `calibration_buckets` | Direct Supabase; Edge Function only for parameterized named windows |
| Pick Detail | `v_pick_clv_live` / `pick_settlements` row + open & close `line_snapshots` | Direct Supabase |
| Archive | `v_pick_archive`, keyset-paginated | Direct Supabase (native range/limit) |
| Account/Settings | `user_settings` (% stake only) | Direct Supabase read/write, RLS `auth.uid()`-scoped |
| Login | Supabase Auth session | `supabase-js`, JWT cookie |

---

## 5. Cross-team contract (as reconciled)

- **Reads:** Frontend → Supabase directly (PostgREST/`supabase-js`), authenticated + RLS-scoped. No proxy.
- **Writes:** only the Backend pipeline, via service-role key (bypasses RLS). Plus each user editing their
  own `user_settings`.
- **Publish handshake:** pipeline writes all picks + flips `model_runs.status → 'success'` in one
  transaction, then fires Frontend's revalidate webhook. Frontend shows "picks pending" until then.
- **Naming:** endpoints/views reconciled to Database's final names (`record_summary`, `mv_clv_trend`,
  `mv_roi_curve`, `calibration_buckets`, `v_todays_picks`, `v_pick_archive`, `v_pick_clv_live`).
  Idempotency key reconciled to `UNIQUE(game_id, market, model_run_id)`.
- **Book consistency:** `picks.market_fair_prob`/`market_odds_american` and
  `pick_settlements.closing_prob` must reference the **same book (Pinnacle)** — mixing books at
  generation vs. close makes CLV no longer apples-to-apples.
- **Odds cadence:** 2 snapshots/game (open + close) → line-movement is an open→close pair, not a chart.
- **Stakes:** percent-only in v1; no $ persisted.

---

## 6. Critic's review — consolidated findings & how they were resolved

The Critic's overall read: *no plan had a fatal flaw; all fixes are foldable pre-build.* Backend's draft
was the most operationally mature; Database's schema was strong on immutability but had a point-in-time
input-capture gap and a likely-accidental public-read RLS setting; Frontend's design was strong but
assumed data (continuous odds, $ bankroll) the other legs couldn't cheaply provide or had deferred.

| # | Finding | Resolution |
|---|---|---|
| 1 | **Picks publicly readable before login** — Supabase anon key isn't secret, so a `public` RLS policy would let anyone pull the slate via PostgREST, bypassing login | **Fixed** — RLS scoped `TO authenticated` only, explicit anon-deny (§3.5) |
| 2 | **Only model outputs stored, not inputs** — no odds-movement or lineup/injury/weather state → breaks Frontend line-movement UI, doc §11 testability, and doc §5 leakage auditability | **Fixed** — typed `line_/lineup_/injury_/weather_snapshots` + `raw_snapshots` archive, one reconciled design (§3.2) |
| 3 | **Odds budget caps displayable granularity** — ~500 req/mo → no continuous line feed | **Fixed** — 2 snapshots/game; Frontend shows discrete open→close, not a live sparkline (§2.5, §4) |
| 4 | **Pinnacle may be under `eu`, not `us`** on The Odds API — wrong region silently burns credits / corrupts the CLV anchor | **[OPEN — verify before build]** — confirm region param + add a fail-loud assertion that responses contain Pinnacle |
| 5a | Frontend assumed $ bankroll; Database deferred it | **Fixed** — percent-only stakes in v1 (also removes a mutability risk) |
| 5b | Backend idempotency key `(game_id, market, model_version)` ≠ Database `UNIQUE(…, model_run_id)` | **Fixed** — reconciled to `model_run_id` (§5) |
| 5c | Frontend's revalidation webhook wasn't called by Backend's pipeline | **Fixed** — added to job F / end-of-run step (§2.3) |
| — | Atomic daily publish so no partial slate renders | **Fixed** — single-transaction picks + status flip (§2.4) |
| — | Silent bad data (empty/partial responses that don't throw) | **Recommended** — per-stage data-quality assertions in the pipeline |
| — | Backup needs read-only cred + restore validation; CI secret-exposure via `pull_request` triggers | **Noted** — scoped credential (§3.6); keep secrets off PR-triggered workflows |
| — | Scraping sources have no outage fallback | **Recommended** — stale-cache fallback with recorded staleness, not hard failure |
| — | ROI over-weighted vs. CLV on Model Record | **Fixed** — ROI subordinated, N shown everywhere (§4.1) |

---

## 7. Open decisions for you (the human)

1. **[doc §11] Line-movement as a model input** — now with a hard constraint: the free odds budget only
   supports a **discrete open-to-close gap** (~4–5 snapshots/day), not continuous steam detection. The
   FDR-gated test should therefore be defined narrowly as **"open→close gap magnitude/direction,"** not
   the doc's original "steam detection" framing — the go/no-go on inclusion survives, but the *scope of
   what's testable* is smaller than the doc implies. Update the build-spec language accordingly.
   *Default to filter-only if it fails.*
2. **Injury-latency alpha (doc §3.5) may be structurally untestable on free data.** The six alpha
   hypotheses split into two structurally different categories: **latency-based** (injury-latency —
   edge from being *faster* than the market) vs. **computation/interaction-based** (bullpen fatigue,
   wind×orientation, umpire environment, early-season SIERA-vs-ERA, Stuff+ for promoted arms — edge from
   doing a computation the market doesn't bother with). MLB StatsAPI's IL feed is roughly
   public-simultaneous with the market, so the **latency** category structurally can't produce an edge on
   free data regardless of a CLV test — worth **deprioritizing** rather than spending effort confirming a
   null. The other **five are unaffected** by this finding; the doc should not lump all six together.
3. **Historical Pinnacle closing-line source for backtesting** — genuinely unresolved; no free source
   found (matches doc §7's open item). Going-*forward* capture is free; pre-launch backtest history is
   not. May warrant a **bounded, one-time paid exception** to the $0 rule for backtest data only — a
   scope call only you can make.
4. **The Odds API region param** — verify Pinnacle is reachable (likely `eu`, not `us`) before build; add
   a fail-loud assertion. Cheap to check, expensive to get wrong (silent CLV corruption).
5. **StatsAPI roster/IL timestamp validity** — spot-check that historical timestamps reflect true
   public-availability time, not batch-updated internal time, before trusting any backtest CLV (doc §5.1).
6. **`raw_snapshots` / snapshot-table retention** — *resolved* to scoped-categories-only + a monthly
   size-check with R2 cold-archive fallback (§3.6); left here only as an item to monitor, not decide.
7. **Backup restore path** — validate end-to-end (monthly restore-into-scratch-DB), not just dump-success.
8. **Supabase auto-pause trigger** — verify whether the 7-day-idle pause keys on PostgREST/API-gateway
   traffic vs. a raw `postgres://` connection; hedge by routing at least one daily write through the REST
   layer regardless (the heartbeat job #H, plus in-season writes, should cover this once confirmed).
9. **GitHub Actions 60-day auto-disable** — verify whether it keys on commit vs. workflow-run activity;
   cheap mitigation either way (a trivial periodic commit).
10. **The Odds API ToS** — confirm the free tier permits **displaying** fetched odds / derived edge to
    end users of a live product (some providers restrict free tiers to personal/research use only). Read
    the current ToS before launch. Sits alongside item 3 as pre-launch due diligence, not an assertion
    that it's fine.
11. **Legal/positioning** — surfacing betting picks to users carries jurisdiction-dependent legal and
    responsible-gambling obligations; confirm positioning (informational/research vs. advice) and keep the
    responsible-gambling disclaimer (§4.1) before any non-personal use.

---

## 8. Bottom line

A genuinely $0, autonomous MLB picks web app is feasible on **GitHub Actions (compute/cron) → Supabase
(Postgres/Auth/RLS) → Next.js on Vercel Hobby**, with Frontend reading Postgres directly and the pipeline
as the only writer. The design is integrity-first: append-only picks and typed point-in-time snapshots
preserve the model doc's leakage discipline and make CLV trustworthy. The binding constraints are all
**data**, not compute: the ~500 req/mo odds budget (caps line-movement to open→close), the absence of a
free historical Pinnacle source (blocks backtest CLV until resolved), and free-data feeds whose latency
may not support the injury-latency alpha. None of these are architectural blockers — they are the four
decisions in §7 that gate moving from plan to build.
```