import type {
  GameStatus,
  ModelRunRow,
  PickClvLiveRow,
  Side,
  TodaysPickRow,
} from "@/lib/types/rows";
import { etDate } from "@/lib/time";

/**
 * A plausible four-game MLB slate: two games already past their close (badge
 * reads "closed — CLV") and two still open, recommended and declined picks
 * side by side, edges inside the 1–6% band the model actually produces, and
 * one negative-edge row kept on the board because CLV is tracked on every
 * evaluated game (doc §7), not only on the bets.
 *
 * Dates are computed at call time rather than hard-coded so the slate is
 * always "today" in ET and the pending/off-day logic in lib/slate.ts is
 * exercised the way it will be in production.
 */

interface GameSeed {
  gameId: number;
  externalGameId: string;
  hour: number;
  minute: number;
  status: GameStatus;
  closed: boolean;
  park: string;
  home: [string, string];
  away: [string, string];
}

interface MarketSeed {
  market: string;
  side: Side;
  line: number | null;
  odds: number;
  fair: number;
  raw: number;
  model: number;
  kelly: number;
  recommended: boolean;
  /** latest_fair_prob on the most recent snapshot, for v_pick_clv_live. */
  latestFair: number;
  latestOdds: number;
}

const GAMES: readonly (GameSeed & { markets: readonly MarketSeed[] })[] = [
  {
    gameId: 9101, externalGameId: "776312", hour: 18, minute: 40,
    status: "in_progress", closed: true, park: "Citizens Bank Park",
    home: ["PHI", "Philadelphia Phillies"], away: ["ATL", "Atlanta Braves"],
    markets: [
      { market: "moneyline", side: "home", line: null, odds: -118, fair: 0.533, raw: 0.552, model: 0.5482, kelly: 0.0079, recommended: true, latestFair: 0.5288, latestOdds: -112 },
      { market: "total", side: "under", line: 9, odds: -104, fair: 0.508, raw: 0.519, model: 0.5169, kelly: 0, recommended: false, latestFair: 0.5131, latestOdds: -109 },
      { market: "spread", side: "home", line: -1.5, odds: 126, fair: 0.439, raw: 0.47, model: 0.4652, kelly: 0.0138, recommended: true, latestFair: 0.4455, latestOdds: 121 },
    ],
  },
  {
    gameId: 9102, externalGameId: "776318", hour: 19, minute: 10,
    status: "in_progress", closed: true, park: "Fenway Park",
    home: ["BOS", "Boston Red Sox"], away: ["NYY", "New York Yankees"],
    markets: [
      { market: "moneyline", side: "away", line: null, odds: -128, fair: 0.548, raw: 0.5905, model: 0.5812, kelly: 0.018, recommended: true, latestFair: 0.5605, latestOdds: -136 },
      { market: "total", side: "over", line: 8.5, odds: -105, fair: 0.509, raw: 0.531, model: 0.5265, kelly: 0.0092, recommended: true, latestFair: 0.5042, latestOdds: -101 },
      { market: "spread", side: "away", line: -1.5, odds: 118, fair: 0.455, raw: 0.472, model: 0.4681, kelly: 0, recommended: false, latestFair: 0.4612, latestOdds: 113 },
    ],
  },
  {
    gameId: 9103, externalGameId: "776324", hour: 21, minute: 40,
    status: "scheduled", closed: false, park: "T-Mobile Park",
    home: ["SEA", "Seattle Mariners"], away: ["HOU", "Houston Astros"],
    markets: [
      { market: "moneyline", side: "home", line: null, odds: 104, fair: 0.488, raw: 0.515, model: 0.5108, kelly: 0.0119, recommended: true, latestFair: 0.4903, latestOdds: 101 },
      { market: "total", side: "over", line: 8, odds: -108, fair: 0.517, raw: 0.532, model: 0.5289, kelly: 0, recommended: false, latestFair: 0.5162, latestOdds: -107 },
      { market: "spread", side: "home", line: 1.5, odds: -142, fair: 0.582, raw: 0.654, model: 0.6412, kelly: 0.0311, recommended: true, latestFair: 0.5847, latestOdds: -144 },
    ],
  },
  {
    gameId: 9104, externalGameId: "776331", hour: 21, minute: 45,
    status: "scheduled", closed: false, park: "Oracle Park",
    home: ["SF", "San Francisco Giants"], away: ["LAD", "Los Angeles Dodgers"],
    markets: [
      { market: "moneyline", side: "away", line: null, odds: -155, fair: 0.5985, raw: 0.6502, model: 0.639, kelly: 0.0244, recommended: true, latestFair: 0.6011, latestOdds: -157 },
      { market: "total", side: "under", line: 7.5, odds: -112, fair: 0.5245, raw: 0.545, model: 0.5401, kelly: 0.0081, recommended: true, latestFair: 0.5223, latestOdds: -110 },
      { market: "spread", side: "away", line: -1.5, odds: 102, fair: 0.488, raw: 0.479, model: 0.4805, kelly: 0, recommended: false, latestFair: 0.4869, latestOdds: 103 },
    ],
  },
];

const RUN_ID = 4471;
const MODEL_VERSION_ID = 31;

function startTime(date: string, hour: number, minute: number): string {
  // ET is UTC-4 during the MLB season; the fixture only needs to be plausible.
  const utcHour = hour + 4;
  const dayOffset = Math.floor(utcHour / 24);
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + dayOffset);
  at.setUTCHours(utcHour % 24, minute, 0, 0);
  return at.toISOString();
}

function lockedAt(date: string): string {
  return `${date}T14:05:00.000Z`; // 10:05 AM ET publish
}

let pickId = 51_200;

export function todaysPicksFixture(): TodaysPickRow[] {
  const date = etDate();
  let id = pickId;
  return GAMES.flatMap((g) =>
    g.markets.map((m): TodaysPickRow => ({
      id: id++,
      game_id: g.gameId,
      game_date: date,
      sport: "mlb",
      market: m.market,
      side: m.side,
      line: m.line,
      player_id: null,
      stat_type: null,
      raw_model_prob: m.raw,
      model_prob: m.model,
      market_fair_prob: m.fair,
      market_odds_american: m.odds,
      book: "pinnacle",
      edge_pct: Number((m.model - m.fair).toFixed(5)),
      recommended: m.recommended,
      kelly_stake_fraction: m.kelly,
      pick_locked_at: lockedAt(date),
      run_date: date,
      pass_type: "confirmed",
      model_version_id: MODEL_VERSION_ID,
      external_game_id: g.externalGameId,
      start_time_utc: startTime(date, g.hour, g.minute),
      game_status: g.status,
      park_name: g.park,
      home_team_code: g.home[0],
      home_team_name: g.home[1],
      away_team_code: g.away[0],
      away_team_name: g.away[1],
    })),
  );
}

export function clvLiveFixture(): PickClvLiveRow[] {
  const date = etDate();
  let id = pickId;
  return GAMES.flatMap((g) =>
    g.markets.map((m): PickClvLiveRow => ({
      pick_id: id++,
      game_id: g.gameId,
      sport: "mlb",
      market: m.market,
      side: m.side,
      line: m.line,
      book: "pinnacle",
      locked_fair_prob: m.fair,
      locked_odds_american: m.odds,
      pick_locked_at: lockedAt(date),
      latest_odds_american: m.latestOdds,
      latest_fair_prob: m.latestFair,
      latest_captured_at: g.closed
        ? startTime(date, g.hour, g.minute - 5)
        : `${date}T16:30:00.000Z`,
      latest_is_closing: g.closed,
      clv_pct_live: Number((m.latestFair - m.fair).toFixed(5)),
    })),
  );
}

export function modelRunFixture(): ModelRunRow {
  const date = etDate();
  return {
    id: RUN_ID,
    model_version_id: MODEL_VERSION_ID,
    sport: "mlb",
    run_date: date,
    pass_type: "confirmed",
    status: "success",
    github_run_id: "17742308841",
    created_at: `${date}T13:50:00.000Z`,
    updated_at: lockedAt(date),
  };
}

export const fixtureGameCount = GAMES.length;
