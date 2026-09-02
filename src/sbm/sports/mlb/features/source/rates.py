"""Counting stats -> the rates `features/` consumes, weighted by recency.

Every function here takes the per-game rows `reads.py` fetched and returns one
value per entity, EWMA-weighted over game order (model doc §10.1). Numerator
and denominator are weighted *separately* and divided afterwards (§4.6) —
`recency.recency_weighted_by_entity` is the one place that happens, and a rate
computed per game and then averaged would be a mean of means, which is a
different number.

Pure: no I/O, no clock. `as_of` arrives as an argument.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from sbm.sports.mlb.features.recency import RATE, recency_weighted_by_entity

HALF_LIFE_GAMES = 12.0
"""Model doc §10.1 fixes EWMA over rolling windows but names no half-life. A
starter makes ~32 starts a season, so 12 games weights roughly the last two
months at over half — long enough to survive one bad outing, short enough to
track a real change in stuff. Engineering default, not a doc number: it is the
single most consequential free parameter here and belongs in a tuning sweep
once there is settled history to sweep against."""

LEAGUE_HR_PER_FB = 0.135
"""xFIP's defining move: replace a pitcher's own home runs with the league rate
applied to his fly balls, because HR/FB is barely a pitcher skill and is the
noisiest part of ERA at one season's sample. ~13.5% is the modern MLB norm.

Recomputing this from the data each run was considered and rejected: it would
make every historical feature value depend on the window the job happened to
pull, so the same game would score differently on two different days and no
backtest would reproduce. A fixed constant is wrong by a little, forever, in
the same direction — which standardisation absorbs."""

REQUIRED_COLUMNS = (
    "game_date", "pitches", "csw", "batters_faced", "outs", "strikeouts",
    "walks", "hit_by_pitch", "ground_balls", "fly_balls", "line_drives", "popups",
)
"""Every column `pitching_rates` reads. Both read functions that feed it —
`fn_pitcher_game_form` and `fn_bullpen_game_form` — must return all of them,
which is asserted against the SQL itself in
`tests/unit/mlb_features/test_rate_contract.py`."""

FIP_CONSTANT = 3.336
"""Scales xFIP onto the ERA scale. Same fixed-vs-recomputed argument as above.

CALIBRATED, not taken from a reference. cFIP exists precisely to place FIP on
the ERA scale and is re-derived every season, so a borrowed value is wrong for
this data by construction. This one is solved so that the innings-weighted
league xFIP over 386 pitchers with 20+ IP lands on `columns.XFIP_LEAGUE_AVG`
(4.00), which is the constant `model/columns.py` standardises against.

That alignment is the whole point and it is not cosmetic. The first value tried
here was 3.10, giving a league mean of 3.76 — so every pitcher standardised to
about 0.38 sd better than average, every opposing starter looked good, and the
model projected suppressed run totals for the entire league. A centring error
in a z-score input is invisible in any single number and biases every one.

If `XFIP_LEAGUE_AVG` ever moves, this must be re-solved against it. The
measured spread is sd 0.82 against `XFIP_SCALE`'s 0.60, so z-scores here run
about 35% wider than that constant assumes — a real mismatch, left alone
because `XFIP_SCALE` is `model`'s constant to set and changing it silently
would rescale every coefficient calibrated against it."""


def utc_aligned(history: pd.DataFrame, as_of: datetime) -> tuple[pd.DataFrame, datetime]:
    """Put `game_date` and `as_of` in the same timezone before they are compared.

    `game_date` is a DATE in Postgres and parses to a naive datetime64, while
    `as_of.ts` is timezone-aware UTC throughout the pipeline (`AsOf` requires
    it). `recency_weighted_by_entity` re-applies the point-in-time filter as a
    guard, and pandas raises `TypeError: Invalid comparison between
    dtype=datetime64[us] and datetime` rather than silently coercing — which is
    the right behaviour and the reason this is normalised rather than papered
    over with a bare comparison.

    A calendar date becomes midnight UTC. That is a widening, not a shift: the
    SQL already restricted to `game_date < as_of`'s date, so no row this
    touches is near the boundary.
    """
    dates = history["game_date"]
    if dates.dt.tz is None:
        history = history.assign(game_date=dates.dt.tz_localize("UTC"))
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    return history, as_of


def _weighted(
    history: pd.DataFrame, *, entity: str, events: str, opportunities: str, as_of: datetime
) -> pd.Series:
    """One EWMA rate per entity, indexed by entity. NaN where no history."""
    if history.empty:
        return pd.Series(dtype=float)
    history, as_of = utc_aligned(history, as_of)
    folded = recency_weighted_by_entity(
        history,
        entity_col=entity,
        events_col=events,
        opportunities_col=opportunities,
        captured_at_col="game_date",
        half_life_games=HALF_LIFE_GAMES,
        as_of=as_of,
    )
    return folded[RATE]


def _totals(history: pd.DataFrame, entity: str) -> pd.DataFrame:
    """Unweighted season sums — the denominators that are counts, not rates.

    `innings_pitched` is a *volume*, so recency weighting it would be
    meaningless: a pitcher who threw 180 innings has thrown 180 innings
    regardless of when. Only rates get the EWMA.
    """
    if history.empty:
        return pd.DataFrame()
    return history.groupby(entity).sum(numeric_only=True)


def pitching_rates(history: pd.DataFrame, *, entity: str, as_of: datetime) -> pd.DataFrame:
    """xFIP, CSW%, GB% and innings pitched per entity.

    `entity` is `player_id` for starters and `pitching_team` for bullpens; the
    columns are identical, which is why one function serves both.
    """
    columns = ["xfip", "csw_pct", "gb_pct", "innings_pitched"]
    if history.empty:
        return pd.DataFrame(columns=columns, dtype=float)

    missing = sorted(set(REQUIRED_COLUMNS) - set(history.columns))
    if missing:
        # Named rather than left to pandas. This fired once in production as a
        # bare `KeyError: 'csw'` three frames inside `recency.py`, because
        # `fn_bullpen_game_form` aggregated every counting stat except that one
        # — a mismatch between a SQL RETURNS TABLE and this function's inputs,
        # which no type checker sees and which the unit tests missed by only
        # ever feeding the bullpen path an empty result.
        raise KeyError(
            f"pitching_rates is missing {missing} for entity={entity!r}. The read "
            "function feeding it must return every column in REQUIRED_COLUMNS — see "
            "db/migrations/018 and tests/unit/mlb_features/test_rate_contract.py."
        )

    work = history.assign(
        _balls_in_play=history["ground_balls"]
        + history["fly_balls"]
        + history["line_drives"]
        + history["popups"],
        _free_passes=history["walks"] + history["hit_by_pitch"],
    )
    csw = _weighted(work, entity=entity, events="csw", opportunities="pitches", as_of=as_of)
    gb = _weighted(
        work, entity=entity, events="ground_balls", opportunities="_balls_in_play", as_of=as_of
    )
    k = _weighted(
        work, entity=entity, events="strikeouts", opportunities="batters_faced", as_of=as_of
    )
    bb = _weighted(
        work, entity=entity, events="_free_passes", opportunities="batters_faced", as_of=as_of
    )
    fb = _weighted(
        work, entity=entity, events="fly_balls", opportunities="batters_faced", as_of=as_of
    )
    totals = _totals(work, entity)

    out = pd.DataFrame(index=totals.index)
    out["csw_pct"] = csw
    out["gb_pct"] = gb
    out["innings_pitched"] = totals["outs"] / 3.0
    # Batters faced per inning from this entity's OWN totals, not a league
    # constant: a strikeout pitcher faces fewer men per inning than a
    # contact pitcher, and that difference is exactly what converts a
    # per-batter rate back onto the per-inning ERA scale.
    outs_per_bf = (totals["outs"] / totals["batters_faced"].replace(0, pd.NA)).astype(float)
    out["xfip"] = xfip_from_rates(
        k_rate=k, bb_rate=bb, fb_rate=fb, bf_per_inning=3.0 / outs_per_bf
    )
    return out[columns]


def xfip_from_rates(
    *,
    k_rate: pd.Series,
    bb_rate: pd.Series,
    fb_rate: pd.Series,
    bf_per_inning: pd.Series,
) -> pd.Series:
    """xFIP from per-batter-faced rates rather than season totals.

    The textbook form is `(13*FB*lgHR/FB + 3*(BB+HBP) - 2*K) / IP + C` over
    totals. Factoring out batters faced turns every term into a rate and leaves
    a single `BF/IP` multiplier:

        xFIP = (BF/IP) * (13*fb_rate*lgHR/FB + 3*bb_rate - 2*k_rate) + C

    That rearrangement is what lets the EWMA reach xFIP at all — season totals
    cannot be recency-weighted without becoming a different statistic, whereas
    each rate can be, and `bf_per_inning` is a stable volume ratio taken from
    unweighted totals.

    `bf_per_inning` is per-entity rather than a league constant (~4.3): a
    strikeout pitcher faces fewer men per inning than a contact pitcher, and
    that gap is precisely what maps a per-batter rate back onto the ERA scale.

    NaN in, NaN out — a pitcher with no history reaches
    `columns._or_default`'s league-average substitution instead of being handed
    an invented number.
    """
    per_bf = 13.0 * fb_rate * LEAGUE_HR_PER_FB + 3.0 * bb_rate - 2.0 * k_rate
    return per_bf * bf_per_inning + FIP_CONSTANT


def batting_xwoba(history: pd.DataFrame, *, as_of: datetime) -> pd.DataFrame:
    """Club xwOBA per (club, opposing hand), EWMA-weighted.

    Indexed by `(batting_team, opp_hand)` because `features/offense.py` resolves
    the split against tonight's opposing starter — collapsing it would remove
    the only thing `xwoba_vs_opp_hand` is for.
    """
    if history.empty:
        return pd.DataFrame(columns=["xwoba"], dtype=float)
    work = history.assign(_key=history["batting_team"] + "|" + history["opp_hand"])
    rate = _weighted(
        work, entity="_key", events="xwoba_sum", opportunities="plate_appearances", as_of=as_of
    )
    index = pd.MultiIndex.from_tuples(
        [tuple(str(k).split("|", 1)) for k in rate.index], names=["batting_team", "opp_hand"]
    )
    return pd.DataFrame({"xwoba": rate.to_numpy()}, index=index)
