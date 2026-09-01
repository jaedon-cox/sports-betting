"""ET wall-clock helpers, and the DST guard every cron-scheduled job runs.

**The problem.** GitHub Actions cron is UTC-only and has no timezone field,
but every cadence in backend doc §2.4 is stated in ET ("~8am ET", "hourly 10am
ET -> first pitch"). ET is UTC-4 for most of the season and UTC-5 outside it,
so a single UTC cron drifts by an hour twice a year. The MLB regular season
sits entirely inside DST, but the postseason can run past the first Sunday in
November and Job H runs year-round, so "it never matters" is not true.

**The fix, and why it is a guard rather than arithmetic.** Each ET-sensitive
workflow schedules *two* crons — the UTC time for the target ET hour under
EDT, and the one under EST — and the job's first action is
`is_intended_run(...)`, which compares the actual ET wall clock against the
target. Exactly one of the two fires inside the window; the other exits 0
immediately. The cost is one extra billed minute per duplicated trigger
(GitHub bills whole minutes per invocation, backend doc §2.2), which is why
only the jobs whose ET hour is load-bearing carry the duplicate.

`WINDOW_MINUTES` is 45 rather than something tight because scheduled workflows
are queued, not guaranteed: a cron can fire many minutes late under load. 45
absorbs that and still cleanly separates the two triggers, which are 60
minutes apart by construction.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
"""Named zone, not a fixed offset — the whole point is that it knows about DST."""

WINDOW_MINUTES = 45
"""How late after its target ET time a trigger still counts as the intended one."""


def now_utc() -> datetime:
    """The one clock read in this package. Jobs take `now` as an argument so
    every one of them is testable at an arbitrary instant."""
    return datetime.now(UTC)


def to_et(moment: datetime) -> datetime:
    """`moment` in ET. Requires an aware datetime — a naive one here would be
    silently interpreted as the runner's local zone, which is UTC on Actions
    and something else on a laptop."""
    if moment.tzinfo is None:
        raise ValueError("clock helpers require a timezone-aware datetime")
    return moment.astimezone(ET)


def slate_date(moment: datetime) -> date:
    """The ET calendar date this instant belongs to.

    This is `games.game_date` / `model_runs.run_date` — StatsAPI's
    `officialDate` (backend doc §3.2). Never `date.today()`: a 10pm-ET
    first pitch is already tomorrow in UTC, so a UTC date would file the
    West-coast wave under the wrong slate.
    """
    return to_et(moment).date()


def minutes_since_et_time(moment: datetime, hour: int, minute: int = 0) -> float:
    """Signed minutes from today's ET `hour:minute` to `moment`.

    Positive means the target has passed. Computed on the ET calendar day
    `moment` falls in, so it stays correct across a UTC date boundary.
    """
    local = to_et(moment)
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (local - target).total_seconds() / 60.0


def is_intended_run(
    moment: datetime, hour: int, minute: int = 0, *, window_minutes: int = WINDOW_MINUTES
) -> bool:
    """Is this invocation the one meant for ET `hour:minute` today?

    True for a trigger that fired at the target or up to `window_minutes`
    after it. The DST-duplicate cron lands exactly 60 minutes away and is
    therefore False — see the module docstring.
    """
    delta = minutes_since_et_time(moment, hour, minute)
    return 0.0 <= delta < window_minutes


def is_within_et_hours(moment: datetime, start_hour: int, end_hour: int) -> bool:
    """Is `moment`'s ET hour inside `[start_hour, end_hour]`, inclusive?

    For the jobs whose cadence is a *range* rather than an instant (Job B is
    hourly 10am ET -> first pitch). A range guard needs no DST duplicate: the
    workflow schedules the union of both offsets' UTC hours and this trims the
    one hour that is outside the ET range on whichever side of DST we are on.
    """
    return start_hour <= to_et(moment).hour <= end_hour


def et_day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of one ET slate date, as UTC instants.

    What a query filtering `captured_at_utc` or `start_time_utc` for "that
    day's games" needs — the ET day is 24h wide but its UTC endpoints move
    with DST, so they are derived from the zone rather than assumed.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=ET)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)
