"""The eight scheduled jobs (backend doc §2.4), one module per job A-H.

Run one with `python -m sbm.jobs <letter>`; `runner.py` maps the letter, wraps
the call in its `pipeline_runs` start/finish pair, and turns the outcome into
an exit code. `.github/workflows/` is the cron layer and `.github/workflows/
README.md` lists every secret an operator must set.

| Job | Cadence | Does |
|---|---|---|
| A | ~8am ET | schedule, teams, weather forecast, **the day's opening odds** |
| B | hourly 10am ET -> first pitch | roster/IL |
| C | ~3h pre-game | Pass A on projected lineups — research, not the official pick |
| D | ~T-45min | Pass B on confirmed lineups — **the official pick**, published atomically |
| E | ~6 cluster triggers/day | closing-line sweep of any game inside its window |
| F | nightly ~4am ET | results, outcomes, CLV, calibration buckets, matviews |
| G | weekly / on demand | full historical re-run; writes nothing |
| H | weekly, year-round | heartbeat, so the offseason cannot idle Supabase into a pause |

The shared modules under these: `context`/`config`/`clock` (wiring, secrets, the
DST guard), `slate_ingest` (schedule -> teams/games + the id maps every job
needs), `odds_sweep` + `pacing` (one priced snapshot, and whether to spend it),
`scoring`/`pricing`/`picks`/`model_pass` (the C/D body), `rpc` (the Postgres
functions `db` ships), `archive` (the `raw_snapshots` drain), `slate` and
`revalidate` (what the frontend reads).
"""
