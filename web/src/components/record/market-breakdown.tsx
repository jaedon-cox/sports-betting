import { ClvValue } from "@/components/clv/clv-value";
import { relative } from "@/lib/clv";
import { formatPercent, formatSignedPercent, humanize } from "@/lib/format";
import { recordLine, type RecordTotals } from "@/lib/record";

export function MarketBreakdown({
  rows,
}: {
  rows: { market: string; totals: RecordTotals }[];
}) {
  return (
    <table className="ledger">
      <thead>
        <tr>
          <th scope="col">Market</th>
          <th scope="col" className="text-right">Evaluated</th>
          <th scope="col" className="text-right">Bet</th>
          <th scope="col" className="text-right">W-L-P</th>
          <th scope="col" className="text-right">Avg CLV</th>
          <th scope="col" className="text-right">CLV &gt; 0</th>
          <th scope="col" className="text-right">Avg edge</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ market, totals }) => (
          <tr key={market}>
            <td data-label="Market">
              <span className="text-[11px] uppercase tracking-placard text-chalk/70">
                {humanize(market)}
              </span>
            </td>
            <td data-label="Evaluated" className="n">
              <span className="num">{totals.nEvaluated.toLocaleString("en-US")}</span>
            </td>
            <td data-label="Bet" className="n">
              <span className="num text-chalk/60">
                {totals.nRecommended.toLocaleString("en-US")}
              </span>
            </td>
            <td data-label="W-L-P" className="n">
              <span className="num">{recordLine(totals)}</span>
            </td>
            <td data-label="Avg CLV" className="n">
              <ClvValue
                measure={totals.avgClvRelative === null ? null : relative(totals.avgClvRelative)}
              />
            </td>
            <td data-label="CLV > 0" className="n">
              <span className="num text-chalk/70">{formatPercent(totals.clvPositiveRate, 1)}</span>
            </td>
            <td data-label="Avg edge" className="n">
              <span className="num text-chalk/60">{formatSignedPercent(totals.avgEdge)}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
