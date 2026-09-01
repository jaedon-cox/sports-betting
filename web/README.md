# web — Night Ledger

Next.js 14 (App Router) frontend for the MLB +EV picks system. Built against
`docs/backend-frontend-database-planning.md` §4 (pages, aesthetic, auth, read
paths) and §5 (cross-team contract).

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # production build
npm run typecheck  # tsc --noEmit
```

## No Supabase project yet

`src/lib/supabase/config.ts` exports `isSupabaseConfigured`, and every reader in
`src/lib/data/` branches on it exactly once:

- **Configured** — Server Components query the real views through `supabase-js`,
  RLS-scoped to the caller's session. No proxy, no REST layer (§4.3).
- **Unconfigured** — typed fixtures from `src/lib/fixtures/`, and a banner on
  every page saying so.

Wiring a real project is setting two env vars (see `.env.example`); no component
changes. A *configured* project that errors does **not** fall back to fixtures —
it throws and `app/error.tsx` renders, because plausible fake numbers during an
outage are worse than an outage.

The fixtures are typed as the row types in `src/lib/types/rows.ts`, which are
transcribed column-for-column from `db/views/*.sql`. Drop a column from a view
and the fixture stops compiling.

## Caching and revalidation

Push-based, per §2.3 ("a `curl` step at the end of each successful run hits
Frontend's revalidate endpoint. No polling, no websockets") and §5's publish
handshake.

### Endpoint — for `pipeline`

```
POST /api/revalidate
Header: x-revalidate-secret: $REVALIDATE_SECRET
Body:   optional JSON, {"tags": ["slate", "archive"]}
```

The secret travels **in the `x-revalidate-secret` header only**. It is never
read from the body or the query string: a query-string secret ends up in
referrer headers, proxy logs and browser history.

Empty or absent body means "a slate published" and revalidates `slate` +
`archive` — the common case, and what the publish job should send. Every call
also revalidates the paths `/`, `/record`, `/archive`.

| Tag | Invalidates the reads behind | Send it after |
|---|---|---|
| `slate` | `v_todays_picks`, `v_pick_clv_live`, `model_runs` — the Today's Picks board | every successful publish run |
| `archive` | `v_pick_archive` and the per-pick detail reads (`pick_settlements`, `line_snapshots`) | a publish (new pending rows) **and** settlement (outcomes land) |
| `record` | `record_summary`, `mv_clv_trend`, `mv_roi_curve`, `calibration_buckets` | the nightly settlement job, after the matview refresh |
| `reference` | the `markets` lookup | only when a market is added — effectively never |

An unrecognised tag is a `400` rather than a silent no-op, so a typo in a job
script fails loudly instead of quietly serving stale picks forever.

```bash
# End of a successful publish run (Job A–E): new picks are live.
curl -fsS -X POST "$SITE_URL/api/revalidate" \
  -H "x-revalidate-secret: $REVALIDATE_SECRET"

# End of the nightly settlement run (Job F): rollups and matviews changed.
curl -fsS -X POST "$SITE_URL/api/revalidate" \
  -H "x-revalidate-secret: $REVALIDATE_SECRET" \
  -H "content-type: application/json" \
  -d '{"tags":["record","archive"]}'
```

Responses: `200 {"revalidated":true,...}` · `400` unknown tag · `401` bad or
missing secret (constant-time compare) · `405` on GET — a GET revalidate
endpoint is triggerable by any third-party `<img>` tag · `503` if
`REVALIDATE_SECRET` is unset on the deployment.

### What is actually cached

Supabase GETs are tagged into Next's **Data Cache** by
`createServerSupabase(tags)`, so a page view costs no database request between
publishes. `revalidateTag` is the operative invalidation.

**The boundary, which is load-bearing:** a tagged client is only ever used for
relations whose RLS is `USING (true)` for `authenticated` — every signed-in
reader sees byte-identical rows, so a shared cache entry can leak nothing
between users. `user_settings` is per-user under `auth.uid()` and is read
through an **untagged** client, and `/account` is `force-dynamic`. Do not tag
a client that reads a user-scoped relation.

`middleware.ts` is the only auth gate on the signed-in pages: they no longer
re-check the session, which halves auth round-trips per view and keeps them out
of the dynamic-render path. Anything added to the middleware `matcher`
exclusion list is therefore published publicly.

### Why the pages still build as `ƒ`

Two independent reasons, both real:

1. `/`, `/record` and `/archive` read `searchParams` (scope toggle, range
   selector, archive filters are URL state so a view is shareable). In the App
   Router that opts a page out of static rendering, full stop — no route
   segment config changes it.
2. The Supabase client reads the session cookie for RLS, and `cookies()` forces
   dynamic rendering.

Reason 1 is inherent to the design and is not worth undoing — moving that state
off the URL would cost the shareable filtered views and the no-JS rendering.

Reason 2 is removable. Until it is, the Data Cache is the layer doing the work,
and `revalidatePath` is wired and correct for the moment it changes.

### Open decision: should `/picks/[id]` render statically?

**Deliberately not taken.** `/picks/[id]` is the one data page with no
`searchParams`, so it is the only one that could become genuinely ISR-cached
per pick. Doing so requires a Supabase read that carries no per-request session,
and both routes there are cross-team calls rather than a frontend choice:

| Option | What it costs |
|---|---|
| **A — service-role key held by the frontend** | Amends §5, which currently assigns service-role to the pipeline alone. The key would bypass RLS entirely, so `middleware.ts` becomes the *only* thing preventing public exposure of the whole product. |
| **B — `anon` SELECT grant on the four read views** | A `db` migration. Same consequence: the views become readable by anyone holding the anon key, so middleware is again the single gate. |

Both trade a defence-in-depth layer for a cache. That is a reasonable trade for
data that is identical for every reader, but it is the lead's and `db`'s call,
not the frontend's.

**Where the change goes if it is taken:** `createServerSupabase()` in
`src/lib/supabase/server.ts` — when `tags` are supplied, build the client with
supabase-js's plain `createClient` (no `cookies()`) instead of
`createServerClient`, then add `export const revalidate = DATA_TTL_SECONDS` to
`src/app/(app)/picks/[id]/page.tsx`. Nothing else moves; the tagged-fetch
plumbing and the webhook already do the right thing. Do **not** extend the same
treatment to `/account` or anything else reading `user_settings` — see the
boundary above.

## Two ways every query silently becomes `never[]`

Both produce the identical, baffling symptom: `.select()` results type as
`never`, every row property is a "does not exist on type 'never'" error, and
there is **no error at the definition site** telling you why.

1. **Row types must be `type` aliases, not `interface`.** An `interface` has no
   implicit index signature, so it fails supabase-js's `Record<string, unknown>`
   constraint on `GenericTable`/`GenericView`, the whole `Database` generic is
   rejected, and every relation degrades to `never`. `src/lib/types/rows.ts` is
   all `type` aliases for this reason — do not "tidy" them into interfaces.
2. **`@supabase/ssr` must be version-matched to `@supabase/supabase-js`.** This
   project pins **0.12.5**. Version 0.5.2 — which is what a naive
   `npm i @supabase/ssr` resolved to against supabase-js 2.112 — imports
   `GenericSchema` from `@supabase/supabase-js/dist/module/lib/types`, a path
   that no longer exists in 2.112. The failed import makes the `Schema` generic
   resolve to `any`, and every row degrades to `never` exactly as in (1). It
   also breaks contextual typing of the `cookies.setAll` callback, which shows
   up as an unrelated-looking implicit-`any` error in `middleware.ts`.

If you upgrade or re-resolve either package and the data layer suddenly stops
typechecking, check (2) before you touch any of your own code.

## Known unknowns — written, typechecked, never executed

There has never been a Supabase project, so the entire live path is compile-time
verified only. Everything below works in fixture mode by a different code path
and should be the first test list when a real project is wired:

- **The keyset pagination predicate.** `src/lib/data/archive.ts` expresses the
  row-value comparison `(game_date, id) < (cursor)` as PostgREST's
  `.or("game_date.lt.X,and(game_date.eq.X,id.lt.Y)")`. The syntax and the
  index usage against `ix_picks_archive_keyset` are both unverified.
- **The games count read.** `.select("id", { count: "exact", head: true })` in
  `src/lib/data/todays-picks.ts`, used to tell an off-day from a pending slate.
- **Matview reads through PostgREST.** `record_summary`, `mv_clv_trend` and
  `mv_roi_curve`. `db/policies/002` GRANTs them to `authenticated`, but a
  matview also has to be reachable in PostgREST's exposed schema, and Postgres
  supports no RLS on matviews at all — so GRANT is the *only* control on them.
- **The magic-link callback.** `src/app/auth/callback/route.ts` handles both
  `?code=` (PKCE) and `?token_hash=&type=`; only one of those will be live,
  depending on how the Supabase email template is configured.
- **The Data Cache.** Fixture mode never issues a `fetch`, so no cache hit has
  ever been observed. Confirm that a second page view between publishes costs
  zero Supabase requests, and that `POST /api/revalidate` actually clears them.

## What this needs from `db`

Logged during wave 2; no `db` teammate was spawned to act on them.

- **Reconcile the two CLV definitions.** `pick_settlements.clv_pct` is relative,
  `v_pick_clv_live.clv_pct_live` is absolute, and they are ~2× apart at typical
  prices. The frontend refuses to mix them (see below), but one of the two
  should be renamed so the ambiguity stops at the source.
- **Confirm the three matviews are exposed to `authenticated` through
  PostgREST** — see the known-unknowns entry above.
- **A rollup grain for favourite/underdog and edge-bucket splits.** §4.1 item 3
  asks for them; `record_summary` rolls up by `(rollup_date, sport, market)`
  only, so they are not buildable and the Record page says so in a footnote.
- **A slate-status source.** To tell "no games today" from "today has not
  published yet", the frontend counts `games` rows for the ET date. A status
  row published by the pipeline would be a better signal than a count.
- **`user_settings.bankroll_usd` is dead weight.** §5 is percent-only, so the
  frontend reads it but never writes it; the bankroll input is `localStorage`.
  Either drop the column or decide it is out of scope deliberately.
- **A session-less read path, if `/picks/[id]` should be statically rendered** —
  see "Open decision" above. Needs a call from the lead and `db` together, since
  either option makes `middleware.ts` the single gate on the whole product.

## Auth

Invite-only magic link (§4.4). Admin invites via `auth.admin.inviteUserByEmail()`
with self-serve signup disabled; `signInWithOtp({ shouldCreateUser: false })` is
the frontend's half of that. `middleware.ts` refreshes the session and redirects
unauthenticated visitors to `/login?next=…` before a protected route renders.

`app/auth/callback/route.ts` accepts both link shapes — `?code=` (PKCE, the
`@supabase/ssr` default) and `?token_hash=&type=` (the `{{ .TokenHash }}` email
template) — so either Supabase Auth configuration works.

## Two CLV units

`pick_settlements.clv_pct` (and therefore `record_summary` / `mv_clv_trend`) is
**relative**: `(closing_prob − bet_prob) / bet_prob`.
`v_pick_clv_live.clv_pct_live` is **absolute**: `latest_fair_prob −
locked_fair_prob`. Same name, ~2× apart at typical prices.

`src/lib/clv.ts` is the only place either is converted or formatted. Relative
renders as a percent (`+2.1% rel`), absolute as basis points (`+25 bps abs`), so
the two differ in notation as well as label. `components/clv/clv-value.tsx` is
the only component that prints a CLV. They are never averaged or co-plotted.

## Conventions

- No `any` anywhere; `supabase-js` is bound to `src/lib/types/database.ts`.
  Row types must be `type` aliases, not `interface` — see "Two ways every query
  silently becomes `never[]`" above before changing either.
- Server Components by default. `"use client"` only for charts, the split-flap,
  the bankroll (localStorage), and the two form-state components.
- Stakes are percentages. The bankroll input is display-only, lives in
  `localStorage`, and is never written to `user_settings` (§5).
