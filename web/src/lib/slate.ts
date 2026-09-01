import type { ModelRunRow, PickClvLiveRow, TodaysPickRow } from "@/lib/types/rows";

/**
 * Pure shaping for the Today's Picks page. v_todays_picks is deliberately
 * flat (one row per pick) and the frontend owns the grouping (§4.5), so this
 * is where a slate becomes games.
 */

export interface GameGroup {
  gameId: number;
  externalGameId: string;
  startTimeUtc: string | null;
  status: TodaysPickRow["game_status"];
  parkName: string | null;
  home: { code: string; name: string };
  away: { code: string; name: string };
  picks: TodaysPickRow[];
}

export function groupByGame(rows: readonly TodaysPickRow[]): GameGroup[] {
  const byGame = new Map<number, GameGroup>();
  for (const row of rows) {
    let group = byGame.get(row.game_id);
    if (!group) {
      group = {
        gameId: row.game_id,
        externalGameId: row.external_game_id,
        startTimeUtc: row.start_time_utc,
        status: row.game_status,
        parkName: row.park_name,
        home: { code: row.home_team_code, name: row.home_team_name },
        away: { code: row.away_team_code, name: row.away_team_name },
        picks: [],
      };
      byGame.set(row.game_id, group);
    }
    group.picks.push(row);
  }
  return [...byGame.values()].sort((a, b) =>
    (a.startTimeUtc ?? "").localeCompare(b.startTimeUtc ?? ""),
  );
}

export type SlateScope = "all" | "recommended";

export function applyScope(
  rows: readonly TodaysPickRow[],
  scope: SlateScope,
): TodaysPickRow[] {
  return scope === "recommended" ? rows.filter((r) => r.recommended) : [...rows];
}

export interface SlateTotals {
  nShown: number;
  nRecommended: number;
  nEvaluated: number;
  /** Sum of kelly_stake_fraction over recommended picks — % of bankroll (§5). */
  exposure: number;
  avgEdge: number | null;
}

export function summarize(
  all: readonly TodaysPickRow[],
  shown: readonly TodaysPickRow[],
): SlateTotals {
  const recommended = all.filter((r) => r.recommended);
  const edges = shown.map((r) => r.edge_pct).filter((e): e is number => e !== null);
  return {
    nShown: shown.length,
    nRecommended: recommended.length,
    nEvaluated: all.length,
    exposure: recommended.reduce((a, r) => a + r.kelly_stake_fraction, 0),
    avgEdge: edges.length === 0 ? null : edges.reduce((a, e) => a + e, 0) / edges.length,
  };
}

/**
 * Two empty states, not one (§4.1 item 7). An off-day is a day with no games;
 * "pending" is a day with games whose confirmed run has not published yet —
 * v_todays_picks keeps serving the last known-good slate until it does, so
 * "there are rows" is not the same question as "today has published."
 */
export type SlateState = "ready" | "pending" | "off_day";

export function slateState(input: {
  today: string;
  gamesToday: number;
  run: ModelRunRow | null;
  picksForToday: number;
}): SlateState {
  if (input.gamesToday === 0) return "off_day";
  if (input.run === null || input.run.run_date !== input.today) return "pending";
  if (input.picksForToday === 0) return "pending";
  return "ready";
}

/** pick_id -> live CLV row, for the per-game status badge. */
export function indexClv(rows: readonly PickClvLiveRow[]): Map<number, PickClvLiveRow> {
  return new Map(rows.map((r) => [r.pick_id, r]));
}

export interface GameCloseState {
  closed: boolean;
  /** Mean ABSOLUTE live CLV across the game's picks; see lib/clv.ts. */
  meanAbsoluteClv: number | null;
  n: number;
}

export function gameCloseState(
  group: GameGroup,
  clv: Map<number, PickClvLiveRow>,
): GameCloseState {
  const rows = group.picks
    .map((p) => clv.get(p.id))
    .filter((r): r is PickClvLiveRow => r !== undefined);
  const closed = rows.some((r) => r.latest_is_closing === true);
  const values = rows
    .filter((r) => r.latest_is_closing === true)
    .map((r) => r.clv_pct_live)
    .filter((v): v is number => v !== null);
  return {
    closed,
    n: values.length,
    meanAbsoluteClv:
      values.length === 0 ? null : values.reduce((a, v) => a + v, 0) / values.length,
  };
}
