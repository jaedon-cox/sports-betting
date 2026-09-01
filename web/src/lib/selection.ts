import type { Side } from "@/lib/types/rows";

/**
 * Renders a pick as a bettor reads it. Deliberately driven by `side` and
 * `line` rather than by a switch on market names — a new market (a player
 * prop, an NFL spread) must not require editing this (CLAUDE.md rule 7).
 */
export function selectionLabel(
  row: { side: Side; line: number | null; player_id: string | null; stat_type: string | null },
  home: string,
  away: string,
): string {
  const line =
    row.line === null
      ? ""
      : ` ${row.line > 0 ? "+" : "−"}${Math.abs(row.line).toFixed(1)}`;

  if (row.side === "over" || row.side === "under") {
    const subject = row.stat_type ? `${row.player_id ?? ""} ${row.stat_type}`.trim() : "";
    const total = row.line === null ? "" : ` ${Math.abs(row.line).toFixed(1)}`;
    return `${subject ? `${subject} ` : ""}${row.side === "over" ? "Over" : "Under"}${total}`;
  }
  return `${row.side === "home" ? home : away}${line}`;
}
