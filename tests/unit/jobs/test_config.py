"""Config: the two failure modes that would take a job down over a default."""

from __future__ import annotations

import pytest

from sbm.core.pricing.kelly import DEFAULT_KELLY_FRACTION as CORE_KELLY
from sbm.jobs.config import DEFAULT_KELLY_FRACTION, JobConfig, MissingSecret


def test_kelly_default_mirrors_core() -> None:
    """`config.py` copies this constant instead of importing it, so that Jobs B
    and H stay httpx-only (see its docstring). This is the guard that keeps the
    copy honest — `core.pricing.kelly` remains the source of truth."""
    assert DEFAULT_KELLY_FRACTION == CORE_KELLY


def test_unset_actions_variables_arrive_as_empty_strings() -> None:
    """`vars.X` interpolates to "" when unset rather than dropping the env var,
    so a naive float(get(...)) would fail on a *default* — the worst place."""
    config = JobConfig.from_env(
        {"SBM_EDGE_THRESHOLD": "", "SBM_N_DRAWS": "  ", "SITE_URL": "", "SBM_SPORT": ""}
    )
    assert config.edge_threshold == 0.0
    assert config.n_draws == 100_000
    assert config.sport == "mlb"
    assert config.site_url is None


def test_explicit_values_win() -> None:
    config = JobConfig.from_env({"SBM_EDGE_THRESHOLD": "0.02", "SBM_DAILY_ODDS_CREDITS": "9"})
    assert (config.edge_threshold, config.daily_odds_credits) == (0.02, 9)


def test_secrets_raise_at_use_not_at_construction() -> None:
    """Job H needs no Odds API key and Job B triggers no revalidation; requiring
    every secret up front would fail the cheap jobs for a credential they never
    touch."""
    config = JobConfig.from_env({})
    with pytest.raises(MissingSecret, match="ODDS_API_KEY"):
        config.require_odds_api_key()
    with pytest.raises(MissingSecret, match="SITE_URL"):
        config.require_revalidate()
    with pytest.raises(MissingSecret, match="REVALIDATE_SECRET"):
        JobConfig.from_env({"SITE_URL": "https://x.test"}).require_revalidate()
