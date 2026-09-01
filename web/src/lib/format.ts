/**
 * Every number the user reads passes through here. Formatting is centralised
 * because the aesthetic depends on it: fixed decimal places keep the
 * tabular-numeral columns rectangular, and a stray toFixed(3) somewhere
 * breaks the ledger grid (§4.2).
 */

export const EM_DASH = "—";

/** American odds always carry an explicit sign: +150, −135. */
export function formatAmericanOdds(odds: number | null): string {
  if (odds === null) return EM_DASH;
  return odds > 0 ? `+${odds}` : `−${Math.abs(odds)}`;
}

/** Probability -> "54.2%". */
export function formatProbability(p: number | null, digits = 1): string {
  if (p === null) return EM_DASH;
  return `${(p * 100).toFixed(digits)}%`;
}

/** Signed fraction -> "+3.42%" / "−1.10%". Used for edge_pct. */
export function formatSignedPercent(v: number | null, digits = 2): string {
  if (v === null) return EM_DASH;
  return `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(digits)}%`;
}

/**
 * Fraction -> "1.25%". Used for Kelly stake, exposure and rates. Negatives
 * take the typographic minus, matching formatSignedPercent — a mono column
 * that mixes "-" and "−" reads as a rendering bug.
 */
export function formatPercent(v: number | null, digits = 2): string {
  if (v === null) return EM_DASH;
  const sign = v < 0 ? "−" : "";
  return `${sign}${Math.abs(v * 100).toFixed(digits)}%`;
}

/** Kelly units -> "+0.84u" / "−1.20u". Never dollars (§5). */
export function formatUnits(v: number | null, digits = 2): string {
  if (v === null) return EM_DASH;
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}u`;
}

/** Unsigned units — a staked total, which is never negative. */
export function formatUnitsStaked(v: number | null, digits = 2): string {
  if (v === null) return EM_DASH;
  return `${v.toFixed(digits)}u`;
}

/** Display-only dollar figure, derived client-side from a local bankroll. */
export function formatUsd(v: number): string {
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: v < 100 ? 2 : 0,
  });
}

export function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

/** Title-cases a market/side key for display without hard-coding the set (rule 7). */
export function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
