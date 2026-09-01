import Link from "next/link";

import { ClvValue } from "@/components/clv/clv-value";
import { Chip } from "@/components/ui/primitives";
import { relative } from "@/lib/clv";
import { formatAmericanOdds, formatSignedPercent, humanize } from "@/lib/format";
import { selectionLabel } from "@/lib/selection";
import { etDayLabel } from "@/lib/time";
import type { Outcome, PickArchiveRow } from "@/lib/types/rows";

const OUTCOME_TONE: Record<Outcome, "positive" | "negative" | "neutral"> = {
  win: "positive",
  loss: "negative",
  push: "neutral",
  void: "neutral",
};

export function ArchiveTable({ rows }: { rows: PickArchiveRow[] }) {
  return (
    <table className="ledger">
      <thead>
        <tr>
          <th scope="col">Date</th>
          <th scope="col">Game</th>
          <th scope="col">Market</th>
          <th scope="col">Selection</th>
          <th scope="col" className="text-right">Odds</th>
          <th scope="col" className="text-right">Edge</th>
          <th scope="col" className="text-right">Result</th>
          <th scope="col" className="text-right">CLV</th>
          <th scope="col" className="text-right" />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className={row.recommended ? "" : "text-chalk/55"}>
            <td data-label="Date">
              <span className="num text-chalk/70">{etDayLabel(row.game_date)}</span>
            </td>
            <td data-label="Game">
              <span className="num">
                {row.away_team_code}
                <span className="mx-1 text-chalk/30">@</span>
                {row.home_team_code}
              </span>
            </td>
            <td data-label="Market">
              <span className="flex items-center gap-2">
                <span className="text-[11px] uppercase tracking-placard text-chalk/55">
                  {humanize(row.market)}
                </span>
                {row.recommended && <Chip tone="accent">Bet</Chip>}
              </span>
            </td>
            <td data-label="Selection">
              <span className="num">
                {selectionLabel(row, row.home_team_code, row.away_team_code)}
              </span>
            </td>
            <td data-label="Odds" className="n">
              <span className="num">{formatAmericanOdds(row.market_odds_american)}</span>
            </td>
            <td data-label="Edge" className="n">
              <span className="num text-chalk/70">{formatSignedPercent(row.edge_pct)}</span>
            </td>
            <td data-label="Result" className="n">
              {row.outcome ? (
                <Chip tone={OUTCOME_TONE[row.outcome]}>{row.outcome}</Chip>
              ) : (
                <span className="text-[10px] uppercase tracking-placard text-chalk/30">
                  Pending
                </span>
              )}
            </td>
            <td data-label="CLV" className="n">
              <ClvValue measure={row.clv_pct === null ? null : relative(row.clv_pct)} />
            </td>
            <td className="n">
              <Link
                href={`/picks/${row.id}`}
                className="text-[10px] uppercase tracking-placard text-chalk/45 no-underline hover:text-floodlight"
              >
                Detail
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
