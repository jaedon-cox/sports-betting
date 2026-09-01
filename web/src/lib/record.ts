import type { RecordSummaryRow } from "@/lib/types/rows";

/**
 * Rollup composition, matching record_summary.sql / mv_clv_trend.sql exactly:
 * averages are recombined as a weighted numerator over a weighted denominator,
 * never as a mean of daily means, which would overweight low-volume days.
 */
export type RecordTotals = {
  nEvaluated: number;
  nRecommended: number;
  wins: number;
  losses: number;
  pushes: number;
  unitsStaked: number;
  unitsWon: number;
  roi: number | null;
  /** RELATIVE CLV — the units record_summary stores. See lib/clv.ts. */
  avgClvRelative: number | null;
  clvPositiveRate: number | null;
  avgEdge: number | null;
};

export function aggregate(rows: readonly RecordSummaryRow[]): RecordTotals {
  const t = rows.reduce(
    (a, r) => {
      a.nEvaluated += r.n_evaluated;
      a.nRecommended += r.n_recommended;
      a.wins += r.wins;
      a.losses += r.losses;
      a.pushes += r.pushes;
      a.unitsStaked += r.units_staked;
      a.unitsWon += r.units_won;
      if (r.avg_clv_pct !== null) a.clvNum += r.avg_clv_pct * r.n_evaluated;
      if (r.clv_positive_rate !== null) a.posNum += r.clv_positive_rate * r.n_evaluated;
      if (r.avg_edge_pct !== null) a.edgeNum += r.avg_edge_pct * r.n_evaluated;
      return a;
    },
    {
      nEvaluated: 0, nRecommended: 0, wins: 0, losses: 0, pushes: 0,
      unitsStaked: 0, unitsWon: 0, clvNum: 0, posNum: 0, edgeNum: 0,
    },
  );

  const den = t.nEvaluated;
  return {
    nEvaluated: t.nEvaluated,
    nRecommended: t.nRecommended,
    wins: t.wins,
    losses: t.losses,
    pushes: t.pushes,
    unitsStaked: t.unitsStaked,
    unitsWon: t.unitsWon,
    roi: t.unitsStaked === 0 ? null : t.unitsWon / t.unitsStaked,
    avgClvRelative: den === 0 ? null : t.clvNum / den,
    clvPositiveRate: den === 0 ? null : t.posNum / den,
    avgEdge: den === 0 ? null : t.edgeNum / den,
  };
}

export function byMarket(
  rows: readonly RecordSummaryRow[],
  blended: string,
): { market: string; totals: RecordTotals }[] {
  const markets = [...new Set(rows.map((r) => r.market))]
    .filter((m) => m !== blended)
    .sort();
  return markets.map((market) => ({
    market,
    totals: aggregate(rows.filter((r) => r.market === market)),
  }));
}

/** "412–388–9" — wins, losses, pushes, on recommended picks only. */
export function recordLine(t: RecordTotals): string {
  return `${t.wins}-${t.losses}-${t.pushes}`;
}
