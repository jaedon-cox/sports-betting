/** Shared chart ink. Charts get hairlines and one accent, like everything else. */
export const CHART = {
  primary: "#F2EEE3",
  muted: "rgba(242,238,227,0.32)",
  threshold: "rgba(232,163,61,0.55)",
  positive: "#4E9F76",
  negative: "#C15B3E",
  dashes: ["4,3", "1,3", "7,3"],
} as const;

export const AXIS = {
  stroke: "rgba(242,238,227,0.18)",
} as const;

export function tickLabel(
  textAnchor: "start" | "middle" | "end",
  dx = 0,
  dy = 4,
) {
  return {
    fill: "rgba(242,238,227,0.4)",
    fontSize: 10,
    fontFamily: "var(--font-mono)",
    textAnchor,
    dx: -dx,
    dy,
  } as const;
}
