"""Throttle must not sleep when calls are already spaced out, and must sleep
exactly the remaining gap when they aren't — asserted via injected fake
clock/sleep so the test doesn't actually wait."""

from __future__ import annotations

from sbm.sports.mlb.ingest.throttle import Throttle


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_first_call_never_sleeps() -> None:
    fake = FakeClock()
    throttle = Throttle(min_interval_s=1.0, clock=fake.clock, sleep=fake.sleep)
    throttle.wait()
    assert fake.slept == []


def test_second_call_too_soon_sleeps_the_remaining_gap() -> None:
    fake = FakeClock()
    throttle = Throttle(min_interval_s=1.0, clock=fake.clock, sleep=fake.sleep)
    throttle.wait()
    fake.now += 0.3
    throttle.wait()
    assert fake.slept == [0.7]


def test_call_after_gap_already_elapsed_does_not_sleep() -> None:
    fake = FakeClock()
    throttle = Throttle(min_interval_s=1.0, clock=fake.clock, sleep=fake.sleep)
    throttle.wait()
    fake.now += 2.0
    throttle.wait()
    assert fake.slept == []
