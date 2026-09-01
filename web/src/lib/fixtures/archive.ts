import type {
  LineSnapshotRow,
  Outcome,
  PickArchiveRow,
  PickSettlementRow,
  Side,
} from "@/lib/types/rows";
import { etDate, etDateMinusDays } from "@/lib/time";
import { mulberry32, pick, round } from "./rng";

/**
 * 50 slate-days of settled picks plus today's unsettled ones, so the archive
 * exercises keyset pagination, pushes, voids, negative CLV, and the NULL
 * outcome/clv_pct that v_pick_archive's LEFT JOIN produces for a game still
 * in progress.
 */

const TEAMS = [
  "ATL", "PHI", "NYM", "WSH", "MIA", "MIL", "CHC", "STL", "CIN", "PIT",
  "LAD", "SD", "SF", "ARI", "COL", "NYY", "BOS", "TOR", "BAL", "TB",
  "CLE", "DET", "MIN", "KC", "CWS", "HOU", "SEA", "TEX", "LAA", "OAK",
] as const;

const MARKET_SIDES: Record<string, readonly Side[]> = {
  moneyline: ["home", "away"],
  total: ["over", "under"],
  spread: ["home", "away"],
};

const MARKETS = ["moneyline", "total", "spread"] as const;

function lineFor(market: string, rand: () => number): number | null {
  if (market === "moneyline") return null;
  if (market === "spread") return rand() < 0.5 ? -1.5 : 1.5;
  return round(7 + Math.floor(rand() * 5) + (rand() < 0.5 ? 0 : 0.5), 1);
}

function outcomeFor(market: string, rand: () => number): Outcome {
  const r = rand();
  if (market !== "moneyline" && r > 0.97) return "push";
  if (r > 0.995) return "void";
  return r < 0.48 ? "win" : "loss";
}

function build(): PickArchiveRow[] {
  const rand = mulberry32(1903);
  const rows: PickArchiveRow[] = [];
  let id = 50_000;

  for (let day = 50; day >= 0; day -= 1) {
    const date = day === 0 ? etDate() : etDateMinusDays(day);
    const settled = day > 0;
    for (let g = 0; g < 3; g += 1) {
      const home = pick(rand, TEAMS);
      let away = pick(rand, TEAMS);
      while (away === home) away = pick(rand, TEAMS);
      const gameId = 8000 + day * 10 + g;
      const market = pick(rand, MARKETS);
      const sides = MARKET_SIDES[market] as readonly Side[];
      const side = pick(rand, sides);
      const fair = round(0.42 + rand() * 0.22, 5);
      const edge = round(0.008 + rand() * 0.052, 5);
      const model = round(fair + edge, 5);
      const recommended = edge > 0.02;
      const odds = fair > 0.5
        ? -Math.round((fair / (1 - fair)) * 100)
        : Math.round(((1 - fair) / fair) * 100);
      rows.push({
        id: id++,
        game_id: gameId,
        game_date: date,
        sport: "mlb",
        market,
        side,
        line: lineFor(market, rand),
        player_id: null,
        stat_type: null,
        model_prob: model,
        market_fair_prob: fair,
        market_odds_american: odds,
        book: "pinnacle",
        edge_pct: edge,
        recommended,
        kelly_stake_fraction: recommended ? round(edge * 0.55, 4) : 0,
        pick_locked_at: `${date}T14:05:00.000Z`,
        external_game_id: String(770000 + gameId),
        start_time_utc: `${date}T23:${g === 0 ? "05" : g === 1 ? "40" : "10"}:00.000Z`,
        game_status: settled ? "final" : "in_progress",
        home_team_code: home,
        away_team_code: away,
        outcome: settled ? outcomeFor(market, rand) : null,
        // RELATIVE CLV (pick_settlements.clv_pct). Roughly a third negative.
        clv_pct: settled ? round(0.02 + (rand() - 0.42) * 0.16, 4) : null,
        settled_at: settled ? `${date}T04:15:00.000Z` : null,
      });
    }
  }
  // v_pick_archive is read newest-first; the fixture is stored that way too.
  return rows.reverse();
}

let cached: PickArchiveRow[] | null = null;

export function pickArchiveFixture(): PickArchiveRow[] {
  cached ??= build();
  return cached;
}

/**
 * The two odds points that exist per pick (§5: 2 snapshots/game, open+close).
 * Deliberately two rows and never more — the detail page renders them as a
 * pair with a delta, not as a series.
 */
export function lineSnapshotsFixture(row: PickArchiveRow): LineSnapshotRow[] {
  const rand = mulberry32(row.id);
  const openFair = row.market_fair_prob ?? 0.5;
  const closeFair = round(openFair * (1 + (row.clv_pct ?? 0.01)), 5);
  const toOdds = (p: number) =>
    p > 0.5 ? -Math.round((p / (1 - p)) * 100) : Math.round(((1 - p) / p) * 100);
  const base: Omit<LineSnapshotRow, "id" | "price_american" | "implied_prob_devigged" | "captured_at_utc" | "is_closing"> = {
    game_id: row.game_id,
    sport: row.sport,
    market: row.market,
    side: row.side,
    line: row.line,
    devig_method: "power",
    source: row.book,
  };
  return [
    {
      ...base,
      id: row.id * 10,
      price_american: toOdds(openFair),
      implied_prob_devigged: openFair,
      captured_at_utc: row.pick_locked_at,
      is_closing: false,
    },
    {
      ...base,
      id: row.id * 10 + 1,
      price_american: toOdds(closeFair) + (rand() < 0.3 ? 1 : 0),
      implied_prob_devigged: closeFair,
      captured_at_utc: row.start_time_utc ?? row.pick_locked_at,
      is_closing: true,
    },
  ];
}

export function settlementFixture(row: PickArchiveRow): PickSettlementRow | null {
  if (row.outcome === null) return null;
  const bet = row.market_fair_prob ?? 0.5;
  return {
    pick_id: row.id,
    outcome: row.outcome,
    clv_pct: row.clv_pct,
    closing_prob: round(bet * (1 + (row.clv_pct ?? 0)), 5),
    bet_prob: bet,
    settled_at: row.settled_at ?? `${row.game_date}T04:15:00.000Z`,
  };
}
