/**
 * Confidence tier is derived in the frontend (§4.1), never stored: it is a
 * reading aid over edge_pct, not a model output, and persisting it would
 * invite it being treated as one. Thresholds are on the raw edge — the
 * distance between model_prob and the de-vigged market price.
 */
export type ConfidenceTier = "thin" | "standard" | "strong" | "outlier";

export function confidenceTier(edge: number | null): ConfidenceTier | null {
  if (edge === null || edge <= 0) return null;
  if (edge < 0.015) return "thin";
  if (edge < 0.03) return "standard";
  if (edge < 0.05) return "strong";
  // Above ~5% the likelier explanation is a stale line or a bad input, not
  // an edge — flagged rather than celebrated.
  return "outlier";
}

export const TIER_LABEL: Record<ConfidenceTier, string> = {
  thin: "Thin",
  standard: "Standard",
  strong: "Strong",
  outlier: "Outlier — verify",
};
