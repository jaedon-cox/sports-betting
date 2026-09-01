import { ClvValue } from "@/components/clv/clv-value";
import { Figure } from "@/components/ui/primitives";
import { absolute } from "@/lib/clv";
import { formatAmericanOdds, formatProbability } from "@/lib/format";
import { etDayLabel, etStamp } from "@/lib/time";
import type { LineSnapshotRow } from "@/lib/types/rows";

/**
 * Two values and a delta — never a chart (§4.1). The odds cadence is two
 * snapshots per game (§5: open and close), so a line chart would draw
 * granularity that was never captured and invite reading a trend into a
 * single segment.
 */
export function OpenClose({
  open,
  close,
}: {
  open: LineSnapshotRow | null;
  close: LineSnapshotRow | null;
}) {
  const delta =
    open?.implied_prob_devigged != null && close?.implied_prob_devigged != null
      ? close.implied_prob_devigged - open.implied_prob_devigged
      : null;

  return (
    <div className="panel">
      <div className="grid divide-chalk/10 sm:grid-cols-2 sm:divide-x">
        <Snapshot label="Open · at pick" snap={open} />
        <Snapshot label="Close · final line" snap={close} />
      </div>
      <div className="rule-t flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <p className="text-[10px] uppercase tracking-placard text-chalk/40">
          Move, open to close
        </p>
        {delta === null ? (
          <p className="text-sm text-chalk/40">
            No closing snapshot yet — the line is still open.
          </p>
        ) : (
          <>
            <ClvValue measure={absolute(delta)} className="text-xl" />
            <p className="num text-[11px] text-chalk/35">
              {formatAmericanOdds(open?.price_american ?? null)} →{" "}
              {formatAmericanOdds(close?.price_american ?? null)}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Snapshot({
  label,
  snap,
}: {
  label: string;
  snap: LineSnapshotRow | null;
}) {
  return (
    <div className="px-4 py-5">
      <p className="text-[10px] uppercase tracking-placard text-chalk/40">{label}</p>
      {snap === null ? (
        <p className="num mt-3 text-2xl text-chalk/25">—</p>
      ) : (
        <>
          <p className="num mt-2 text-3xl leading-none">
            {formatAmericanOdds(snap.price_american)}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <Figure
              label="Fair prob"
              value={formatProbability(snap.implied_prob_devigged, 2)}
              sub={`de-vig: ${snap.devig_method ?? "—"}`}
            />
            <Figure
              label="Captured"
              value={etStamp(snap.captured_at_utc)}
              sub={etDayLabel(snap.captured_at_utc)}
            />
          </div>
        </>
      )}
    </div>
  );
}
