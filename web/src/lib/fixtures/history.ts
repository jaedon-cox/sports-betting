import type {
  CalibrationBucketRow,
  ClvTrendRow,
  RecordSummaryRow,
  RoiCurveRow,
} from "@/lib/types/rows";
import { etDateMinusDays } from "@/lib/time";
import { mulberry32, round } from "./rng";

/**
 * ~90 days of settled history. The cumulative columns are composed exactly
 * the way mv_clv_trend.sql and mv_roi_curve.sql compose them — a running
 * numerator over a running denominator, never an average of averages — so the
 * fixtures stay internally consistent with the SQL they stand in for.
 *
 * Volume is tuned to land the recommended-bet count under ~2000, which keeps
 * the ROI module's "noise under ~2000 bets" disclaimer truthful rather than
 * decorative.
 */

const DAYS = 90;
export const MARKETS = ["moneyline", "total", "spread"] as const;
export const BLENDED = "blended";

interface DayMarket {
  n_evaluated: number;
  n_recommended: number;
  wins: number;
  losses: number;
  pushes: number;
  units_staked: number;
  units_won: number;
  avg_clv_pct: number;
  clv_positive_rate: number;
  avg_edge_pct: number;
}

function gaussian(rand: () => number): number {
  // Box-Muller; one draw is enough for fixture noise.
  const u = Math.max(rand(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

function dayMarket(rand: () => number, market: string): DayMarket {
  const nEval = 8 + Math.floor(rand() * 7);
  const nRec = Math.max(1, Math.round(nEval * (0.35 + rand() * 0.2)));
  const pushes = market === "moneyline" ? 0 : rand() < 0.12 ? 1 : 0;
  const decided = nRec - pushes;
  const wins = Math.max(0, Math.min(decided, Math.round(decided * (0.522 + gaussian(rand) * 0.085))));
  const losses = decided - wins;
  const staked = round(nRec * (0.011 + rand() * 0.008), 4);
  const perBet = staked / Math.max(nRec, 1);
  const won = round(wins * perBet * 0.93 - losses * perBet, 4);
  return {
    n_evaluated: nEval,
    n_recommended: nRec,
    wins,
    losses,
    pushes,
    units_staked: staked,
    units_won: won,
    avg_clv_pct: round(0.021 + gaussian(rand) * 0.034, 4),
    clv_positive_rate: round(Math.min(0.95, Math.max(0.15, 0.57 + gaussian(rand) * 0.09)), 5),
    avg_edge_pct: round(0.026 + rand() * 0.014, 5),
  };
}

function toRow(date: string, market: string, d: DayMarket): RecordSummaryRow {
  return {
    rollup_date: date,
    sport: "mlb",
    market,
    n_evaluated: d.n_evaluated,
    n_recommended: d.n_recommended,
    wins: d.wins,
    losses: d.losses,
    pushes: d.pushes,
    units_staked: d.units_staked,
    units_won: d.units_won,
    roi_pct: d.units_staked === 0 ? null : round(d.units_won / d.units_staked, 5),
    avg_clv_pct: d.avg_clv_pct,
    clv_positive_rate: d.clv_positive_rate,
    avg_edge_pct: d.avg_edge_pct,
  };
}

function blend(date: string, parts: readonly DayMarket[]): RecordSummaryRow {
  const sum = (f: (d: DayMarket) => number) => parts.reduce((a, d) => a + f(d), 0);
  const nEval = sum((d) => d.n_evaluated);
  const weighted = (f: (d: DayMarket) => number) =>
    round(parts.reduce((a, d) => a + f(d) * d.n_evaluated, 0) / nEval, 5);
  return toRow(date, BLENDED, {
    n_evaluated: nEval,
    n_recommended: sum((d) => d.n_recommended),
    wins: sum((d) => d.wins),
    losses: sum((d) => d.losses),
    pushes: sum((d) => d.pushes),
    units_staked: round(sum((d) => d.units_staked), 4),
    units_won: round(sum((d) => d.units_won), 4),
    avg_clv_pct: weighted((d) => d.avg_clv_pct),
    clv_positive_rate: weighted((d) => d.clv_positive_rate),
    avg_edge_pct: weighted((d) => d.avg_edge_pct),
  });
}

function build(): RecordSummaryRow[] {
  const rand = mulberry32(20260901);
  const rows: RecordSummaryRow[] = [];
  for (let i = DAYS; i >= 1; i -= 1) {
    const date = etDateMinusDays(i);
    const parts = MARKETS.map((m) => dayMarket(rand, m));
    MARKETS.forEach((m, idx) => rows.push(toRow(date, m, parts[idx] as DayMarket)));
    rows.push(blend(date, parts));
  }
  return rows;
}

let cached: RecordSummaryRow[] | null = null;

export function recordSummaryFixture(): RecordSummaryRow[] {
  cached ??= build();
  return cached;
}

/** Mirrors mv_clv_trend.sql: cumulative sum of (avg * n) over cumulative n. */
export function clvTrendFixture(): ClvTrendRow[] {
  const byMarket = new Map<string, { n: number; clv: number; pos: number }>();
  return recordSummaryFixture().map((r) => {
    const acc = byMarket.get(r.market) ?? { n: 0, clv: 0, pos: 0 };
    acc.n += r.n_evaluated;
    acc.clv += (r.avg_clv_pct ?? 0) * r.n_evaluated;
    acc.pos += (r.clv_positive_rate ?? 0) * r.n_evaluated;
    byMarket.set(r.market, acc);
    return {
      rollup_date: r.rollup_date,
      sport: r.sport,
      market: r.market,
      n_evaluated: r.n_evaluated,
      avg_clv_pct: r.avg_clv_pct,
      cum_n_evaluated: acc.n,
      cum_avg_clv_pct: acc.n === 0 ? null : round(acc.clv / acc.n, 5),
      cum_clv_positive_rate: acc.n === 0 ? null : round(acc.pos / acc.n, 5),
    };
  });
}

/** Mirrors mv_roi_curve.sql: cum_units_won / cum_units_staked. */
export function roiCurveFixture(): RoiCurveRow[] {
  const byMarket = new Map<string, { n: number; staked: number; won: number }>();
  return recordSummaryFixture().map((r) => {
    const acc = byMarket.get(r.market) ?? { n: 0, staked: 0, won: 0 };
    acc.n += r.n_recommended;
    acc.staked = round(acc.staked + r.units_staked, 4);
    acc.won = round(acc.won + r.units_won, 4);
    byMarket.set(r.market, acc);
    return {
      rollup_date: r.rollup_date,
      sport: r.sport,
      market: r.market,
      n_recommended: r.n_recommended,
      units_staked: r.units_staked,
      units_won: r.units_won,
      roi_pct: r.roi_pct,
      cum_n_recommended: acc.n,
      cum_units_staked: acc.staked,
      cum_units_won: acc.won,
      cum_roi_pct: acc.staked === 0 ? null : round(acc.won / acc.staked, 5),
    };
  });
}

export function calibrationBucketsFixture(): CalibrationBucketRow[] {
  const rand = mulberry32(77);
  const date = etDateMinusDays(1);
  return Array.from({ length: 10 }, (_, i): CalibrationBucketRow => {
    const bucket = i + 1;
    const mid = (bucket - 0.5) / 10;
    // Middle deciles carry most of the volume, as they do in a real book.
    const n = 40 + Math.round(260 * Math.exp(-((mid - 0.5) ** 2) / 0.045));
    return {
      rollup_date: date,
      sport: "mlb",
      market: BLENDED,
      predicted_bucket: bucket,
      method_version: "isotonic@2026-06-14",
      n,
      avg_predicted_prob: round(mid + (rand() - 0.5) * 0.012, 5),
      actual_win_rate: round(Math.min(0.99, Math.max(0.01, mid + (rand() - 0.5) * 0.07)), 5),
      created_at: `${date}T09:00:00.000Z`,
      updated_at: `${date}T09:00:00.000Z`,
    };
  });
}
