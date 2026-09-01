"""The DST guard — the one piece of these jobs that a UTC-only cron cannot do."""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.clock import (
    et_day_bounds,
    is_intended_run,
    is_within_et_hours,
    minutes_since_et_time,
    slate_date,
    to_et,
)


def test_eight_am_et_is_a_different_utc_hour_either_side_of_dst() -> None:
    summer = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    winter = datetime(2026, 12, 1, 13, 0, tzinfo=UTC)
    assert to_et(summer).hour == to_et(winter).hour == 8


def test_only_the_intended_trigger_survives_the_guard() -> None:
    """Both crons fire; exactly one is 8am ET. That is the whole design."""
    for moment, expected in (
        (datetime(2026, 7, 1, 12, 0, tzinfo=UTC), True),   # 08:00 EDT
        (datetime(2026, 7, 1, 13, 0, tzinfo=UTC), False),  # 09:00 EDT
        (datetime(2026, 12, 1, 12, 0, tzinfo=UTC), False),  # 07:00 EST
        (datetime(2026, 12, 1, 13, 0, tzinfo=UTC), True),  # 08:00 EST
    ):
        assert is_intended_run(moment, 8) is expected, moment


def test_guard_tolerates_a_late_cron_but_not_the_hour_apart_duplicate() -> None:
    on_time = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert is_intended_run(on_time.replace(minute=40), 8) is True   # 40 min late
    assert is_intended_run(on_time.replace(minute=50), 8) is False  # past the window
    assert is_intended_run(on_time.replace(hour=11), 8) is False    # fired early


def test_guard_handles_minute_offsets() -> None:
    """Job D targets 18:15 ET, not a whole hour."""
    assert is_intended_run(datetime(2026, 7, 1, 22, 15, tzinfo=UTC), 18, 15) is True
    assert is_intended_run(datetime(2026, 7, 1, 23, 15, tzinfo=UTC), 18, 15) is False


def test_slate_date_is_the_et_day_not_the_utc_day() -> None:
    """A 10pm ET first pitch is already tomorrow in UTC — filing the West-coast
    wave under the wrong slate is the bug this prevents."""
    late = datetime(2026, 7, 2, 2, 30, tzinfo=UTC)  # 2026-07-01 22:30 ET
    assert slate_date(late).isoformat() == "2026-07-01"


def test_et_day_bounds_track_the_offset() -> None:
    start, end = et_day_bounds(slate_date(datetime(2026, 7, 1, 12, 0, tzinfo=UTC)))
    assert (start.hour, end.hour) == (4, 4)  # EDT: midnight ET is 04:00 UTC
    winter_start, _ = et_day_bounds(slate_date(datetime(2026, 12, 1, 13, 0, tzinfo=UTC)))
    assert winter_start.hour == 5


def test_range_guard_trims_the_out_of_range_hour() -> None:
    assert is_within_et_hours(datetime(2026, 7, 1, 14, 0, tzinfo=UTC), 10, 22) is True
    assert is_within_et_hours(datetime(2026, 7, 1, 13, 0, tzinfo=UTC), 10, 22) is False
    assert is_within_et_hours(datetime(2026, 7, 2, 3, 0, tzinfo=UTC), 10, 22) is False


def test_minutes_since_is_signed() -> None:
    assert minutes_since_et_time(datetime(2026, 7, 1, 12, 30, tzinfo=UTC), 8) == 30.0
    assert minutes_since_et_time(datetime(2026, 7, 1, 11, 30, tzinfo=UTC), 8) == -30.0
