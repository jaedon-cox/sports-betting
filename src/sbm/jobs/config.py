"""Environment configuration for the scheduled jobs (backend doc §2.4).

Every job reads its secrets and knobs through this one module, so the
operator-facing surface is a single table (see `.github/workflows/README.md`)
rather than a grep across eight job files. Secrets have no defaults — a job
pointed at no project must fail before it spends an Odds API credit or writes
a row, not silently no-op — while the tuning knobs default to the doc's own
numbers.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


DEFAULT_SPORT = "mlb"

DEFAULT_KELLY_FRACTION = 0.25
"""25% fractional Kelly (model doc §7). **Mirrors**
`core.pricing.kelly.DEFAULT_KELLY_FRACTION`, which is the source of truth;
`tests/unit/jobs/test_config.py` asserts the two are equal so the copy cannot
drift. It is a copy rather than an import because importing anything under
`sbm.core.pricing` executes that package's `__init__`, which pulls `devig` and
therefore scipy — and this module is imported by every job, including the two
(B and H) whose entire dependency set is otherwise httpx. Backend doc §2.2
bills whole minutes per invocation, and Job B alone runs ~300 times a month,
so a scientific-stack install it never uses is a real line item."""

DEFAULT_N_DRAWS = 100_000
"""Draws/game/side — backend doc §2.2's target for a daily slate run."""

DEFAULT_DAILY_ODDS_CREDITS = 15
"""1 open snapshot (3 credits) + 4 closing sweeps (12) = the doc §2.5 cadence,
15/day x 30 ~= 450 against the 500/month cap. `pacing.py` spends against this."""

DEFAULT_EDGE_THRESHOLD = 0.0
"""**No doc gives this number.** Model doc §7 leaves book limits and execution
realities open, and nothing in the backend doc fills it in either, so it is
deliberately policy rather than a derived constant: `SBM_EDGE_THRESHOLD` is the
env var, and the default of 0.0 means "recommend any strictly positive edge"
(`edge_pct > threshold`, so 0.0 excludes an exactly-zero edge). Raise it to
demand a margin over the de-vigged fair price. It changes only the
`recommended` flag — a below-threshold pick is still written, still priced and
still tracked for CLV (model doc §7)."""


class MissingSecret(RuntimeError):
    """A secret a job needs is unset in the environment.

    Raised at the point of use rather than at construction: Job H needs no
    Odds API key and Job B triggers no revalidation, so requiring every
    secret up front would make the cheap jobs fail for want of a credential
    they never touch.
    """


@dataclass(frozen=True, slots=True)
class JobConfig:
    """Resolved environment for one job invocation."""

    sport: str
    edge_threshold: float
    kelly_fraction: float
    n_draws: int
    daily_odds_credits: int
    git_sha: str
    github_run_id: str | None
    odds_api_key: str | None
    site_url: str | None
    revalidate_secret: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> JobConfig:
        source = os.environ if env is None else env

        def get(name: str, default: object) -> str:
            """Empty means absent.

            An unset GitHub Actions `vars.X` interpolates to the empty string
            rather than dropping the variable, so `float(source.get(...))` on a
            workflow that lists a knob it does not set would raise ValueError —
            a job failing on a *default* is the worst possible failure mode.
            """
            value = source.get(name, "")
            return value.strip() or str(default)

        return cls(
            sport=get("SBM_SPORT", DEFAULT_SPORT),
            edge_threshold=float(get("SBM_EDGE_THRESHOLD", DEFAULT_EDGE_THRESHOLD)),
            kelly_fraction=float(get("SBM_KELLY_FRACTION", DEFAULT_KELLY_FRACTION)),
            n_draws=int(get("SBM_N_DRAWS", DEFAULT_N_DRAWS)),
            daily_odds_credits=int(get("SBM_DAILY_ODDS_CREDITS", DEFAULT_DAILY_ODDS_CREDITS)),
            # GITHUB_SHA is the canonical model version key (backend doc §3.2:
            # `model_versions.git_sha`). Locally it is absent, so 'local' keeps a
            # dev run from silently registering itself as some real commit.
            git_sha=get("GITHUB_SHA", "local"),
            github_run_id=source.get("GITHUB_RUN_ID") or None,
            odds_api_key=source.get("ODDS_API_KEY") or None,
            site_url=source.get("SITE_URL") or None,
            revalidate_secret=source.get("REVALIDATE_SECRET") or None,
        )

    def require_odds_api_key(self) -> str:
        if not self.odds_api_key:
            raise MissingSecret("ODDS_API_KEY is unset — this job makes a priced Odds API call")
        return self.odds_api_key

    def require_revalidate(self) -> tuple[str, str]:
        """(site_url, secret) for the ISR purge. See `revalidate.py`."""
        if not self.site_url:
            raise MissingSecret("SITE_URL is unset — this job revalidates the frontend cache")
        if not self.revalidate_secret:
            raise MissingSecret("REVALIDATE_SECRET is unset — the purge would 401")
        return self.site_url, self.revalidate_secret
