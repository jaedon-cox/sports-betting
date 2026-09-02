"""Pitch-level Statcast -> immutable per-game aggregates, the feature store's grain.

**Why per-game rows rather than nightly snapshots of a season stat.** What a
pitcher did on 30 Aug never changes, so a per-game row is a *fact*, not a
point-in-time observation of a moving number. Any as-of question is then a
`WHERE game_date < as_of` filter, which makes leakage structurally impossible
rather than a discipline the caller has to keep (CLAUDE.md rule 4). It is also
backfillable — Statcast runs to 2015 — so backtest history does not begin the
day the pipeline is switched on, which a snapshot table could never offer.

**Why not FanGraphs.** `pybaseball.py` sources SIERA / xFIP / wRC+ from
FanGraphs, whose `leaders-legacy.aspx` endpoint now answers 403; the module
header recorded that as possibly sandbox-specific and it is not. Everything
here derives from Baseball Savant instead, which also fixes a latent join
hazard: Savant carries MLBAM player ids, the same id space as StatsAPI's
probable pitchers, so no FanGraphs `IDfg` crosswalk is needed.

**SIERA and wRC+ are therefore absent, deliberately.** See `DEFERRED` below.

Pure aggregation, no I/O, no clock: the caller supplies whatever window it
fetched and gets rows back.
"""

from __future__ import annotations

import pandas as pd

DEFERRED = """SIERA (model doc §3.1/§A6) and wRC+ are not computed here.

Both are FanGraphs formulas and FanGraphs is unreachable (403). The agreed v1
substitution is xFIP for pitching and xwOBA for offense — internally consistent
because both come from one source, and supported by code that already exists:
`features/pitcher.py::_siera_with_xfip_fallback` falls back to xFIP whenever
SIERA is null, which is every row this module produces.

TO IMPLEMENT LATER, in priority order:
  1. SIERA — a published regression over K%, BB% and GB%, all three of which
     this module already emits per game. It needs no new data source, only the
     coefficients; write it as `siera(k_pct, bb_pct, gb_pct)` beside `xfip()`
     and populate `pitcher_game_stats.siera`. Until then that column is NULL
     and the fallback carries every pitcher, which silently disables the
     small-sample branch the doc asks for (under 30 IP, prefer xFIP) because
     the fallback is already universal.
  2. wRC+ — needs league and park run environments, and `park_run_factor` has
     no free numeric source (see `features/park.py`), so this is blocked on the
     same gap rather than on effort. xwOBA is descriptive of the same thing but
     is neither park- nor league-adjusted, so cross-era and cross-park
     comparisons are NOT valid on it.
Until (1) lands, `model/columns.py`'s SIERA standardisation is operating on an
xFIP-scaled input; the league-average constant it centres on was chosen for
SIERA and is close but not identical.
"""

WHIFF_DESCRIPTIONS = frozenset({"swinging_strike", "swinging_strike_blocked"})
"""`foul_tip` is contact, not a miss — matching `savant.py`'s CSW definition."""

CALLED_STRIKE = "called_strike"

OUT_EVENTS: dict[str, int] = {
    "field_out": 1,
    "strikeout": 1,
    "force_out": 1,
    "sac_fly": 1,
    "sac_bunt": 1,
    "fielders_choice_out": 1,
    "other_out": 1,
    "sac_fly_double_play": 2,
    "grounded_into_double_play": 2,
    "double_play": 2,
    "strikeout_double_play": 2,
    "triple_play": 3,
}
"""Outs recorded, by PA-ending event.

`fielders_choice` is deliberately 0: Statcast uses it when the batter reaches
and it is `fielders_choice_out` that carries the retired runner, so counting
both would double some outs. Innings pitched is a *denominator* here (xFIP,
per-start workload), so a systematic over-count would deflate every rate.

KNOWN BIAS, measured not assumed: outs recorded on the bases — caught
stealing, pickoffs — end a half-inning without ending a plate appearance, and
Statcast carries no event row for them at all (verified: no `caught_stealing_*`
or `pickoff_*` value appears in a live pull). So `outs` runs slightly light.
Measured over 58 games it is **0.29 outs per game across both clubs, 0.57% of
a nine-inning game**, which inflates every xFIP by roughly the same 0.6%.

That is left uncorrected on purpose. The bias is one-directional and near
identical for every pitcher, and `model/columns.py` standardises these into
z-scores, where a common multiplicative shift is absorbed almost entirely.
Fixing it properly means a StatsAPI boxscore call per game for official innings
pitched — one request per game per day against a 1 req/s throttle — which buys
0.6% on a denominator. Revisit only if a real IP figure is wanted for its own
sake.
"""

GROUND_BALL, FLY_BALL, LINE_DRIVE, POPUP = "ground_ball", "fly_ball", "line_drive", "popup"

XWOBA = "estimated_woba_using_speedangle"
"""Savant fills this for every wOBA-denominator PA, not only batted balls —
strikeouts land at 0.000 and walks at ~0.698, verified against a live pull. The
four events where it is null (`catcher_interf`, `intent_walk`, `sac_bunt`,
`truncated_pa`) are exactly those wOBA excludes, so dropping nulls and taking a
plain mean is the correct denominator rather than an approximation."""

PITCHER_KEY = ["game_pk", "game_date", "pitcher"]
TEAM_KEY = ["game_pk", "game_date", "batting_team", "opp_hand"]


def _sides(pitches: pd.DataFrame) -> pd.DataFrame:
    """Attach which club is batting and which is pitching.

    `inning_topbot == 'Top'` means the away side bats, so the home club is on
    the mound. Statcast states this only as the half-inning label.
    """
    top = pitches["inning_topbot"].astype(str).str.lower().str.startswith("t")
    return pitches.assign(
        batting_team=pitches["away_team"].where(top, pitches["home_team"]),
        pitching_team=pitches["home_team"].where(top, pitches["away_team"]),
    )


def aggregate_pitcher_games(pitches: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, pitcher) with the raw counting stats every rate needs.

    Rates are deliberately NOT computed here. `features/` weights these
    components across games with an EWMA (model doc §10.1), and a rate has to be
    re-derived from summed numerators and denominators to survive that — the
    num/denom-weighted-separately rule (§4.6). Storing `k_pct` per game would
    make the weighted season rate a mean of means, which it is not.
    """
    if pitches.empty:
        return pd.DataFrame(columns=[*PITCHER_KEY, "p_throws", "pitching_team"])

    work = _sides(pitches)
    events = work["events"]
    described = work["description"].astype("string")
    work = work.assign(
        _pitch=1,
        _csw=described.isin(WHIFF_DESCRIPTIONS | {CALLED_STRIKE}).astype("int64"),
        _pa=events.notna().astype("int64"),
        _outs=events.map(OUT_EVENTS).fillna(0).astype("int64"),
        _k=events.isin(["strikeout", "strikeout_double_play"]).astype("int64"),
        _bb=events.isin(["walk", "intent_walk"]).astype("int64"),
        _hbp=(events == "hit_by_pitch").astype("int64"),
        _hr=(events == "home_run").astype("int64"),
        _gb=(work["bb_type"] == GROUND_BALL).astype("int64"),
        _fb=(work["bb_type"] == FLY_BALL).astype("int64"),
        _ld=(work["bb_type"] == LINE_DRIVE).astype("int64"),
        _pu=(work["bb_type"] == POPUP).astype("int64"),
    )
    out = (
        work.groupby(PITCHER_KEY, as_index=False)
        .agg(
            pitches=("_pitch", "sum"),
            csw=("_csw", "sum"),
            batters_faced=("_pa", "sum"),
            outs=("_outs", "sum"),
            strikeouts=("_k", "sum"),
            walks=("_bb", "sum"),
            hit_by_pitch=("_hbp", "sum"),
            home_runs=("_hr", "sum"),
            ground_balls=("_gb", "sum"),
            fly_balls=("_fb", "sum"),
            line_drives=("_ld", "sum"),
            popups=("_pu", "sum"),
            p_throws=("p_throws", "first"),
            pitching_team=("pitching_team", "first"),
            _first_ab=("at_bat_number", "min"),
        )
    )
    return out.assign(is_start=_is_start(out)).drop(columns="_first_ab")


def _is_start(rows: pd.DataFrame) -> pd.Series:
    """The pitcher who faced his side's first batter of the game.

    Derived from `at_bat_number` rather than assumed from row order, because a
    pitcher's rows are grouped by game and not by appearance sequence. A game
    whose feed is missing its opening plate appearances yields no starter for
    that side rather than promoting whoever appears earliest.
    """
    earliest = rows.groupby(["game_pk", "pitching_team"])["_first_ab"].transform("min")
    return rows["_first_ab"].eq(earliest)


def aggregate_team_batting_games(pitches: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, batting club, opposing pitcher hand).

    Split by `p_throws` because `features/offense.py` wants
    `xwoba_vs_opp_hand` — a club's production against the hand it will actually
    see tonight. Summed numerator and denominator, not a mean, for the same
    EWMA reason as above.
    """
    if pitches.empty:
        return pd.DataFrame(columns=[*TEAM_KEY, "plate_appearances", "xwoba_sum"])

    work = _sides(pitches).rename(columns={"p_throws": "opp_hand"})
    scored = work[work[XWOBA].notna()]
    return (
        scored.groupby(TEAM_KEY, as_index=False)
        .agg(plate_appearances=(XWOBA, "size"), xwoba_sum=(XWOBA, "sum"))
    )
