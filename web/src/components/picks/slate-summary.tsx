import { BankrollInput } from "@/components/bankroll/bankroll-ui";
import { FlipNumber } from "@/components/flip/flip-number";
import { Stat } from "@/components/ui/primitives";
import { formatPercent, formatSignedPercent } from "@/lib/format";
import type { SlateTotals } from "@/lib/slate";
import type { ModelRunRow } from "@/lib/types/rows";
import { etStamp } from "@/lib/time";

/**
 * The slate's headline strip. Exposure gets the split-flap treatment (§4.2) —
 * it is the one number on this page that answers "how much of the bankroll is
 * at risk today," which is what the board is for.
 */
export function SlateSummary({
  totals,
  run,
}: {
  totals: SlateTotals;
  run: ModelRunRow | null;
}) {
  return (
    <div className="panel mb-8">
      <p className="rule-b px-4 py-2.5 text-[11px] uppercase tracking-placard text-chalk/45">
        {run
          ? `Picks generated at ${etStamp(run.updated_at)} · ${run.pass_type} pass · model v${run.model_version_id}`
          : "Publish time unavailable"}
      </p>
      <div className="grid gap-8 px-4 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-placard text-chalk/40">
            Today&rsquo;s exposure
          </p>
          <p className="mt-2 text-[2.6rem] leading-none text-floodlight">
            <FlipNumber
              value={formatPercent(totals.exposure)}
              label="Today's exposure"
            />
          </p>
          <p className="num mt-2 text-[10px] uppercase tracking-placard text-chalk/30">
            n = {totals.nRecommended} recommended · % of bankroll
          </p>
        </div>
        <Stat
          label="Picks shown"
          value={totals.nShown}
          n={totals.nEvaluated}
          hint="N is every game the model evaluated today, bet or not."
        />
        <Stat
          label="Average edge"
          value={formatSignedPercent(totals.avgEdge)}
          n={totals.nShown}
          tone={totals.avgEdge !== null && totals.avgEdge > 0 ? "positive" : "neutral"}
        />
        <BankrollInput />
      </div>
    </div>
  );
}
