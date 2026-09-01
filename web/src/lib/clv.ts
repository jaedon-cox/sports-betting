/**
 * CLV has two incompatible definitions live in this schema at once, and they
 * are ~2x apart at typical prices:
 *
 *   RELATIVE  pick_settlements.clv_pct = (closing_prob - bet_prob) / bet_prob
 *             -> feeds record_summary.avg_clv_pct and mv_clv_trend.
 *   ABSOLUTE  v_pick_clv_live.clv_pct_live = latest_fair_prob - locked_fair_prob
 *             -> the pre-settlement / live number only.
 *
 * `db` owns reconciling them. Until then the frontend refuses to average,
 * compare, or co-plot the two, and every rendered CLV figure carries its unit.
 * The two are given deliberately different NOTATION as well as different
 * labels — absolute reads as basis points, relative reads as a percent — so
 * they cannot be confused at a glance either. All conversion lives here; no
 * component multiplies a CLV by 10000 inline.
 */

declare const relativeBrand: unique symbol;
declare const absoluteBrand: unique symbol;

/** Change in win probability as a fraction of the bet's own price. */
export type RelativeClv = number & { readonly [relativeBrand]: true };
/** Change in win probability in probability points (0.004 = 40 bps). */
export type AbsoluteClv = number & { readonly [absoluteBrand]: true };

export const asRelativeClv = (v: number): RelativeClv => v as RelativeClv;
export const asAbsoluteClv = (v: number): AbsoluteClv => v as AbsoluteClv;

export type ClvMeasure =
  | { kind: "relative"; value: RelativeClv }
  | { kind: "absolute"; value: AbsoluteClv };

export const relative = (v: number): ClvMeasure => ({
  kind: "relative",
  value: asRelativeClv(v),
});
export const absolute = (v: number): ClvMeasure => ({
  kind: "absolute",
  value: asAbsoluteClv(v),
});

/** Probability points -> basis points. The only place this factor appears. */
export const absoluteClvToBps = (v: AbsoluteClv): number => v * 10_000;

export const CLV_UNIT = {
  relative: {
    axis: "% of bet price",
    tag: "rel",
    note: "Relative CLV: (closing fair prob − bet fair prob) ÷ bet fair prob. Settled picks only.",
  },
  absolute: {
    axis: "bps of win prob",
    tag: "abs",
    note: "Absolute CLV: closing fair prob − bet fair prob, in probability basis points. Live, pre-settlement.",
  },
} as const;

/** Relative CLV renders as a percent: "+3.2%". */
export function formatRelativeClv(v: RelativeClv | null): string {
  if (v === null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}%`;
}

/** Absolute CLV renders as basis points: "+38 bps". */
export function formatAbsoluteClv(v: AbsoluteClv | null): string {
  if (v === null || Number.isNaN(v)) return "—";
  const bps = absoluteClvToBps(v);
  return `${bps >= 0 ? "+" : "−"}${Math.abs(bps).toFixed(0)} bps`;
}

export function formatClv(measure: ClvMeasure | null): string {
  if (measure === null) return "—";
  return measure.kind === "relative"
    ? formatRelativeClv(measure.value)
    : formatAbsoluteClv(measure.value);
}

/** Sign only — for choosing Turf vs Clay. Zero is neutral, not positive. */
export function clvSign(measure: ClvMeasure | null): -1 | 0 | 1 {
  if (measure === null) return 0;
  const v = measure.value as number;
  return v > 0 ? 1 : v < 0 ? -1 : 0;
}
