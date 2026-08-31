"""Wall-clock rate limiter shared by ingest clients hitting unofficial APIs.

MLB StatsAPI has no published rate limit or SLA (backend doc §2.1) — task 4
requires self-throttling to <=1 req/s rather than trusting the upstream to
push back. `clock`/`sleep` are injectable so tests can assert throttling
behavior without an actual multi-second sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Throttle:
    """Blocks `wait()` until at least `min_interval_s` has passed since the
    previous call to `wait()` on this instance."""

    min_interval_s: float
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_call: float | None = field(default=None, init=False, repr=False)

    def wait(self) -> None:
        now = self.clock()
        if self._last_call is not None:
            remaining = self.min_interval_s - (now - self._last_call)
            if remaining > 0:
                self.sleep(remaining)
                now = self.clock()
        self._last_call = now
