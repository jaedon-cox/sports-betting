"""What every job is handed: a DB client, resolved config, and the instant it
started.

This is also the one place `PostgrestUsageStore` is constructed. That matters
more than it looks: `odds/budget.py` charges credits *before* each HTTP call so
a crash mid-request can never leave spend unaccounted, but that only bounds the
500/month cap if the ledger outlives the runner — and on GitHub Actions nothing
local does (CLAUDE.md rule 8, backend doc §2.5, db/migrations/008's own
header). Wiring `JsonlUsageStore` here instead would look like it worked and
would silently reset the counter to zero on every invocation.

`now` is captured once per job and threaded down rather than re-read, so a job
that straddles midnight ET files all of its rows under one slate date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sbm.jobs.clock import now_utc, slate_date
from sbm.jobs.config import JobConfig
from sbm.odds.budget import OddsBudget
from sbm.odds.budget_store import PostgrestUsageStore
from sbm.store.client import PostgrestClient


@dataclass(frozen=True, slots=True)
class JobContext:
    """One job invocation's wiring."""

    client: PostgrestClient
    config: JobConfig
    now: datetime

    @property
    def slate_date(self) -> date:
        """ET slate date for this invocation (`clock.slate_date`)."""
        return slate_date(self.now)

    def budget(self) -> OddsBudget:
        """The Odds API gate, backed by the durable `odds_budget_usage` ledger."""
        return OddsBudget(store=PostgrestUsageStore(client=self.client))


def build_context(
    *,
    client: PostgrestClient | None = None,
    config: JobConfig | None = None,
    now: datetime | None = None,
) -> JobContext:
    """Construct the real wiring, or accept injected pieces for tests.

    `PostgrestClient()` reads SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY from the
    environment and raises KeyError if either is unset — which is the correct
    failure for a write job pointed at no project.
    """
    return JobContext(
        client=client or PostgrestClient(),
        config=config or JobConfig.from_env(),
        now=now or now_utc(),
    )
