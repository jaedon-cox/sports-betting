import Link from "next/link";

import { StakeAmount } from "@/components/bankroll/bankroll-ui";
import { Chip } from "@/components/ui/primitives";
import { TIER_LABEL, confidenceTier } from "@/lib/confidence";
import {
  formatAmericanOdds,
  formatPercent,
  formatProbability,
  formatSignedPercent,
  humanize,
} from "@/lib/format";
import { selectionLabel } from "@/lib/selection";
import type { TodaysPickRow } from "@/lib/types/rows";

export function MarketRow({
  row,
  home,
  away,
}: {
  row: TodaysPickRow;
  home: string;
  away: string;
}) {
  const tier = confidenceTier(row.edge_pct);
  const edgeTone =
    row.edge_pct === null || row.edge_pct === 0
      ? "text-chalk/55"
      : row.edge_pct > 0
        ? "text-turf"
        : "text-clay";

  return (
    <tr className={row.recommended ? "" : "text-chalk/55"}>
      <td data-label="Market">
        <span className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-placard text-chalk/60">
            {humanize(row.market)}
          </span>
          {row.recommended && <Chip tone="accent">Bet</Chip>}
        </span>
      </td>
      <td data-label="Selection">
        <span className="num font-medium">{selectionLabel(row, home, away)}</span>
      </td>
      <td data-label="Odds" className="n">
        <span className="num">{formatAmericanOdds(row.market_odds_american)}</span>
      </td>
      <td data-label="Model" className="n">
        <span className="num">{formatProbability(row.model_prob)}</span>
      </td>
      <td data-label="Market fair" className="n">
        <span className="num text-chalk/60">
          {formatProbability(row.market_fair_prob)}
        </span>
      </td>
      <td data-label="Edge" className="n">
        <span className={`num ${edgeTone}`}>{formatSignedPercent(row.edge_pct)}</span>
      </td>
      <td data-label="Confidence" className="n">
        <span className="text-[10px] uppercase tracking-placard text-chalk/45">
          {tier ? TIER_LABEL[tier] : "—"}
        </span>
      </td>
      <td data-label="Stake" className="n">
        <span className="num">
          {row.kelly_stake_fraction > 0 ? formatPercent(row.kelly_stake_fraction) : "—"}
        </span>
        <StakeAmount kelly={row.kelly_stake_fraction} />
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
  );
}
