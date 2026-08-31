"""Normalize The Odds API's raw Pinnacle payload into `line_snapshots` rows.

Split from a single module at 244/250 lines, ahead of `pipeline`'s wave-2
edits. The seams follow what each part is coupled to, so a change has one
obvious home:

- `rows.py` — what we *write*. Knows `db`'s schema, not the wire format.
  A `line_snapshots` migration lands here.
- `parse.py` — what we *read*. Knows The Odds API's JSON, not `db`. An
  upstream shape change lands here.
- `normalize.py` — joins the two and owns the skip policy. `normalize_snapshot`
  and `NormalizedSnapshot` live here.

Table shape (backend doc §3.2, reconciled with `db`'s actual
`sbm.store.snapshots.LineSnapshotRow`): game_id, market, side, line,
price_american, implied_prob_devigged, devig_method, captured_at_utc,
source, is_closing.

**Market key**: `"spread"`, not `"run_line"` (see `rows.Market`).

**De-vig**: `core`'s `devig_sides` is the wired default; `power` for all
three markets (see `rows.DEVIG_METHOD`).

**Game-id resolution**: injected, because it needs a lookup this package
doesn't own. It returns `odds/resolution.py`'s `ResolvedGameId`/`Unresolved`
pair, never an `Optional` — a `None` reaching a query filter is how a join
silently returns nothing (`core`'s audit). An unresolvable game is skipped
rather than raised, because two of the three reasons are routine
(doubleheader, off-slate) and only one signals a real upstream problem;
every skip is counted by reason so the caller can tell those apart.

Importing from `sbm.odds.snapshot` keeps working exactly as before the split.
"""

from __future__ import annotations

from sbm.odds.snapshot.normalize import NormalizedSnapshot, normalize_snapshot
from sbm.odds.snapshot.parse import BOOKMAKER
from sbm.odds.snapshot.rows import DEVIG_METHOD, DevigFn, LineSnapshotRow, Market

__all__ = [
    "BOOKMAKER",
    "DEVIG_METHOD",
    "DevigFn",
    "LineSnapshotRow",
    "Market",
    "NormalizedSnapshot",
    "normalize_snapshot",
]
