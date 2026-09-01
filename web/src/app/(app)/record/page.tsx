import { ClvUnitsNote, ClvValue } from "@/components/clv/clv-value";
import { FlipNumber } from "@/components/flip/flip-number";
import { CalibrationChart } from "@/components/record/calibration-chart";
import { ClvTrendChart } from "@/components/record/clv-trend-chart";
import { MarketBreakdown } from "@/components/record/market-breakdown";
import { RangeSelector } from "@/components/record/range-selector";
import { RoiCurve } from "@/components/record/roi-module";
import { EmptyState, PageTitle, Placard, Stat } from "@/components/ui/primitives";
import { relative } from "@/lib/clv";
import { BLENDED_MARKET, RANGES, getRecord, parseRange } from "@/lib/data/record";
import { formatCount, formatPercent, formatUnitsStaked } from "@/lib/format";
import { aggregate, byMarket, recordLine } from "@/lib/record";

/**
 * No `force-dynamic`: this page's output is identical for every signed-in
 * reader, so it must stay eligible for the segment cache and the publish
 * webhook (§2.3). It still renders per request today only because the Supabase
 * client reads the session cookie for RLS — the Supabase reads themselves are
 * tagged into Next's Data Cache, so a view costs no database request between
 * publishes. See web/README.md "Caching and revalidation".
 *
 * Auth is enforced in middleware.ts before this renders (§4.4); the page does
 * not re-check, which also halves the auth round-trips per view.
 */
export const metadata = { title: "Model record" };

export default async function RecordPage({
  searchParams,
}: {
  searchParams: { range?: string };
}) {
  const range = parseRange(searchParams.range);
  const { data } = await getRecord(range);

  const blendedRows = data.summary.filter((r) => r.market === BLENDED_MARKET);
  const totals = aggregate(blendedRows);
  const markets = byMarket(data.summary, BLENDED_MARKET);
  const roiRows = data.roiCurve.filter((r) => r.market === BLENDED_MARKET);

  if (totals.nEvaluated === 0) {
    return (
      <>
        <PageTitle kicker={RANGES[range].label}>Model record</PageTitle>
        <RangeSelector active={range} />
        <div className="mt-8">
          <EmptyState
            title="Nothing settled yet"
            body="No picks in this window have been graded. The record fills in after the nightly settlement job runs."
          />
        </div>
      </>
    );
  }

  return (
    <>
      <PageTitle kicker={RANGES[range].label}>Model record</PageTitle>
      <div className="mb-8">
        <RangeSelector active={range} />
      </div>

      <div className="panel mb-10 grid gap-8 px-4 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-placard text-chalk/40">
            Record · {RANGES[range].label}
          </p>
          <p className="mt-2 text-[2.2rem] leading-none text-chalk">
            <FlipNumber value={recordLine(totals)} label="Win loss push record" />
          </p>
          <p className="num mt-2 text-[10px] uppercase tracking-placard text-chalk/30">
            n = {formatCount(totals.nRecommended)} bets · win-loss-push
          </p>
        </div>
        <Stat
          label="Average CLV"
          value={
            <ClvValue
              measure={totals.avgClvRelative === null ? null : relative(totals.avgClvRelative)}
              showUnit={false}
            />
          }
          unit="rel"
          n={totals.nEvaluated}
          hint="Averaged over every evaluated game, not only the bets."
        />
        <Stat
          label="CLV positive rate"
          value={formatPercent(totals.clvPositiveRate, 1)}
          n={totals.nEvaluated}
          tone={
            totals.clvPositiveRate !== null && totals.clvPositiveRate > 0.5
              ? "positive"
              : "neutral"
          }
        />
        <Stat
          label="Units staked"
          value={formatUnitsStaked(totals.unitsStaked)}
          n={totals.nRecommended}
          hint="Kelly fractions of bankroll. No dollar amount is stored."
        />
      </div>

      <section className="mb-10">
        <Placard>Closing line value · cumulative</Placard>
        <div className="panel px-4 py-5">
          <ClvTrendChart rows={data.clvTrend} blended={BLENDED_MARKET} />
          <ClvUnitsNote />
        </div>
      </section>

      <section className="mb-10">
        <Placard>Calibration</Placard>
        <div className="panel px-4 py-5">
          <CalibrationChart rows={data.calibration} />
          <p className="mt-3 text-[11px] leading-relaxed text-chalk/35">
            Method version{" "}
            <span className="num">{data.calibration[0]?.method_version ?? "—"}</span> ·
            n ={" "}
            <span className="num">
              {formatCount(data.calibration.reduce((a, b) => a + b.n, 0))}
            </span>{" "}
            graded picks across ten deciles. Buckets are pinned to a method
            version so a later re-fit never silently restates the past.
          </p>
        </div>
      </section>

      <section className="mb-10">
        <Placard>By market</Placard>
        <div className="panel">
          <MarketBreakdown rows={markets} />
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-chalk/30">
          Favourite/underdog and edge-bucket splits are not shown: record_summary
          rolls up by market only, so those breakdowns need a rollup grain the
          database does not expose yet.
        </p>
      </section>

      <section className="mb-4 max-w-xl">
        <Placard>Return · secondary</Placard>
        <div className="panel px-4 py-4">
          <div className="flex items-baseline justify-between gap-4">
            <p className="num text-lg text-chalk/70">
              {formatPercent(totals.roi, 1)}{" "}
              <span className="text-[10px] uppercase tracking-placard text-chalk/30">
                on staked units
              </span>
            </p>
            <p className="num text-[10px] uppercase tracking-placard text-chalk/30">
              n = {formatCount(totals.nRecommended)}
            </p>
          </div>
          <div className="mt-3">
            <RoiCurve rows={roiRows} />
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-chalk/35">
            ROI is noise under roughly 2,000 bets. At{" "}
            <span className="num">{formatCount(totals.nRecommended)}</span> it is
            not evidence of skill in either direction — closing line value and
            calibration above are the metrics this model is judged on.
          </p>
        </div>
      </section>
    </>
  );
}
