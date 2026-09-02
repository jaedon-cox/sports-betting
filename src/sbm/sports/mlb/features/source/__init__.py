"""`PostgrestSnapshotSource` — the real point-in-time source `builder.py` wants.

Replaces `_UnwiredSnapshotSource`, which raised on every method because no read
layer existed. Every number here derives from rows strictly earlier than
`as_of`, and that cut is enforced in SQL (db/migrations/018) rather than by
convention, so a caller cannot forget it.

**One instance serves live and backtest** — CLAUDE.md rule 4's "the same
builder serves live and backtest, do not fork them". Nothing here reads a
clock; `as_of` arrives as an argument and everything keys off it. That is
possible only because the stat grain is a per-game *fact* rather than a
snapshot of a moving season aggregate (db/migrations/017's header).

**Missing data is NaN, never a raise.** A pitcher with no history, a club with
an empty form window, a game with no forecast — all reach `model/columns.py`,
whose `_or_default` substitutes the league-average prior (doc §5.4, "assume
average beats crashing the pipeline"). What must never happen is a *fabricated*
number: NaN stays visible downstream, a guess does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from sbm.contracts.feature import AsOf
from sbm.sports.mlb.features.builder import SideFrames
from sbm.sports.mlb.features.source import reads
from sbm.sports.mlb.features.source.context import SCHEDULED_INNINGS, GameContext
from sbm.sports.mlb.features.source.derive import (
    BULLPEN_COLUMNS,
    FORM_WINDOW_DAYS,
    INJURY_LOOKBACK_HOURS,
    OFFENSE_COLUMNS,
    PITCHER_COLUMNS,
    TTO_COLUMNS,
    bullpen_fatigue,
    expected_ip,
    sided_frames,
)
from sbm.sports.mlb.features.source.environment import park_frame, weather_frame
from sbm.sports.mlb.features.source.rates import batting_xwoba, pitching_rates
from sbm.store.client import PostgrestClient

__all__ = ["GameContext", "PostgrestSnapshotSource"]


@dataclass(frozen=True, slots=True)
class PostgrestSnapshotSource:
    """Satisfies `features.builder.SnapshotSource` over the live schema."""

    client: PostgrestClient
    games: Mapping[str, GameContext]
    """external gamePk -> what the job knows about that game (`context.py`)."""
    _cache: dict = field(default_factory=dict, compare=False)
    """Per-instance memo. `builder.build()` calls all six methods for one slate
    at one instant, and three of them need the same starter history — without
    this the same RPC runs three times per run."""

    # -- shared reads ----------------------------------------------------

    def _contexts(self, game_ids: list[str]) -> list[GameContext]:
        """Known games only. An id off this slate is skipped rather than
        raising: `build()` reindexes to `game_ids` and an unknown game becomes
        a row of NaN, which is the honest result."""
        return [self.games[g] for g in game_ids if g in self.games]

    def _since(self, as_of: AsOf) -> date:
        return as_of.ts.date() - timedelta(days=FORM_WINDOW_DAYS)

    def _teams(self, game_ids: list[str]) -> list[str]:
        return sorted({t for c in self._contexts(game_ids) for t in (c.home_team, c.away_team)})

    def _memo(self, key: tuple, build: Callable):
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    def _starters(self, game_ids: list[str], as_of: AsOf):
        """(raw per-game rows, per-pitcher rates) for this slate's starters."""

        def build():
            ids = sorted(
                {
                    pid
                    for ctx in self._contexts(game_ids)
                    for pid in (ctx.home_starter_id, ctx.away_starter_id)
                    if pid is not None
                }
            )
            rows = reads.pitcher_game_form(
                self.client, player_ids=ids, since=self._since(as_of), as_of=as_of.ts.date()
            )
            starts = rows[rows["is_start"].astype(bool)] if not rows.empty else rows
            return rows, pitching_rates(starts, entity="player_id", as_of=as_of.ts)

        return self._memo(("starters", tuple(game_ids), as_of.ts), build)

    def _hands(self, game_ids: list[str], as_of: AsOf) -> dict:
        """MLBAM id -> 'L'/'R', from the pitcher's own recorded appearances.

        Taken from the stat rows rather than from StatsAPI's probable-pitcher
        payload, which carries no handedness — and a starter with no prior
        appearance has no hand here, which correctly leaves the opposing club's
        platoon split unresolvable rather than defaulting it to right-handed.
        """
        raw, _ = self._starters(game_ids, as_of)
        if raw.empty:
            return {}
        return raw.dropna(subset=["throws"]).groupby("player_id")["throws"].last().to_dict()

    def _injuries(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        def build():
            team_ids = sorted(
                {
                    tid
                    for ctx in self._contexts(game_ids)
                    for tid in (ctx.home_team_id, ctx.away_team_id)
                    if tid is not None
                }
            )
            return reads.injury_status(
                self.client,
                team_ids=team_ids,
                since=as_of.ts - timedelta(hours=INJURY_LOOKBACK_HOURS),
                as_of=as_of.ts,
            )

        return self._memo(("injuries", tuple(game_ids), as_of.ts), build)

    def _injury_counts(self, game_ids: list[str], as_of: AsOf) -> pd.Series:
        injuries = self._injuries(game_ids, as_of)
        if injuries.empty:
            return pd.Series(dtype=float)
        return injuries.groupby("team_id").size()

    # -- SnapshotSource --------------------------------------------------

    def pitcher_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        _, rates = self._starters(game_ids, as_of)
        hands = self._hands(game_ids, as_of)
        injured = set(self._injuries(game_ids, as_of).get("player_id", pd.Series(dtype=str)))

        def row(ctx: GameContext, side: str) -> dict:
            pid = getattr(ctx, f"{side}_starter_id")
            form = rates.loc[pid] if pid is not None and pid in rates.index else None
            return {
                # NULL until SIERA is implemented; `features/pitcher.py`'s xFIP
                # fallback carries every row (statcast_games.py::DEFERRED).
                "siera": np.nan,
                "xfip": np.nan if form is None else form["xfip"],
                "csw_pct": np.nan if form is None else form["csw_pct"],
                "gb_pct": np.nan if form is None else form["gb_pct"],
                "hand": hands.get(pid),
                "innings_pitched": np.nan if form is None else form["innings_pitched"],
                "starter_injured": pid is not None and pid in injured,
            }

        return sided_frames(self.games, game_ids, PITCHER_COLUMNS, row)

    def bullpen_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        history = reads.bullpen_game_form(
            self.client, teams=self._teams(game_ids), since=self._since(as_of),
            as_of=as_of.ts.date(),
        )
        rates = pitching_rates(history, entity="pitching_team", as_of=as_of.ts)
        fatigue = bullpen_fatigue(history, as_of)
        unavailable = self._injury_counts(game_ids, as_of)

        def row(ctx: GameContext, side: str) -> dict:
            team = getattr(ctx, f"{side}_team")
            return {
                "fatigue": fatigue.get(team, np.nan),
                "xfip": rates.loc[team]["xfip"] if team in rates.index else np.nan,
                # An IL count over the whole 40-man, not relievers alone:
                # `injury_snapshots` carries no position, so narrowing it would
                # need a roster join this read does not make. Coarser than
                # `features/bullpen.py` asks for, and flagged there.
                "unavailable_arms": float(unavailable.get(getattr(ctx, f"{side}_team_id"), 0)),
            }

        return sided_frames(self.games, game_ids, BULLPEN_COLUMNS, row)

    def offense_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        history = reads.team_batting_form(
            self.client, teams=self._teams(game_ids), since=self._since(as_of),
            as_of=as_of.ts.date(),
        )
        xwoba = batting_xwoba(history, as_of=as_of.ts)
        hands = self._hands(game_ids, as_of)
        key_injuries = self._injury_counts(game_ids, as_of)

        def row(ctx: GameContext, side: str) -> dict:
            team = getattr(ctx, f"{side}_team")
            opp = "away" if side == "home" else "home"
            opp_hand = hands.get(getattr(ctx, f"{opp}_starter_id"))
            value = np.nan
            if opp_hand is not None and (team, opp_hand) in xwoba.index:
                value = xwoba.loc[(team, opp_hand)]["xwoba"]
            return {
                # NULL in v1: wRC+ is a FanGraphs statistic and needs the park
                # factors this repo has no source for. `columns.py` substitutes
                # the league average, so the term is constant across clubs and
                # contributes nothing rather than misleading — offense is
                # carried by xwOBA alone (statcast_games.py::DEFERRED).
                "wrc_plus": np.nan,
                "xwoba_vs_opp_hand": value,
                "key_injuries_count": float(
                    key_injuries.get(getattr(ctx, f"{side}_team_id"), 0)
                ),
            }

        return sided_frames(self.games, game_ids, OFFENSE_COLUMNS, row)

    def tto_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        raw, _ = self._starters(game_ids, as_of)
        per_start = expected_ip(raw)

        def row(ctx: GameContext, side: str) -> dict:
            return {
                "expected_ip": per_start.get(getattr(ctx, f"{side}_starter_id"), np.nan),
                "scheduled_innings": SCHEDULED_INNINGS,
            }

        return sided_frames(self.games, game_ids, TTO_COLUMNS, row)

    def park_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        """Structural facts only — no as-of dependence, since a ballpark's roof
        does not move between snapshots."""
        return park_frame(self.games, game_ids)

    def weather_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        return weather_frame(self.client, self.games, game_ids, as_of)
