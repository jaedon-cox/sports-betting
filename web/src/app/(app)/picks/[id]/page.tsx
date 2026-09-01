import Link from "next/link";
import { notFound } from "next/navigation";

import { ClvUnitsNote, ClvValue } from "@/components/clv/clv-value";
import { OpenClose } from "@/components/detail/open-close";
import { PickFacts } from "@/components/detail/pick-facts";
import { Chip, Figure, PageTitle, Placard } from "@/components/ui/primitives";
import { absolute, relative } from "@/lib/clv";
import { getPickDetail } from "@/lib/data/pick-detail";
import { formatProbability, humanize } from "@/lib/format";
import { selectionLabel } from "@/lib/selection";
import { etClock, etDayLabel, etStamp } from "@/lib/time";

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
export const metadata = { title: "Pick detail" };

export default async function PickDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const id = Number(params.id);
  if (!Number.isInteger(id) || id <= 0) notFound();

  const result = await getPickDetail(id);
  if (result === null) notFound();
  const { pick, liveClv, settlement, open, close } = result.data;

  return (
    <>
      <PageTitle
        kicker={
          <>
            {etDayLabel(pick.game_date)} · {pick.away_team_code} @ {pick.home_team_code} ·{" "}
            {etClock(pick.start_time_utc)} ET
          </>
        }
      >
        {selectionLabel(pick, pick.home_team_code, pick.away_team_code)}
      </PageTitle>

      <div className="mb-10">
        <PickFacts pick={pick} />
      </div>

      <section className="mb-10">
        <Placard>Open → close</Placard>
        <OpenClose open={open} close={close} />
        <p className="mt-3 max-w-2xl text-[11px] leading-relaxed text-chalk/30">
          Two prices exist for this pick and no others: the one it was written
          at, and the closing line. Both are {pick.book} — mixing books between
          the two would make the comparison meaningless.
        </p>
      </section>

      <section className="mb-10">
        <Placard>Result</Placard>
        <div className="panel grid gap-6 px-4 py-6 sm:grid-cols-3 lg:grid-cols-4">
          <div>
            <p className="text-[10px] uppercase tracking-placard text-chalk/40">Outcome</p>
            <p className="mt-2">
              {settlement ? (
                <Chip
                  tone={
                    settlement.outcome === "win"
                      ? "positive"
                      : settlement.outcome === "loss"
                        ? "negative"
                        : "neutral"
                  }
                >
                  {settlement.outcome}
                </Chip>
              ) : (
                <Chip>Not settled</Chip>
              )}
            </p>
            {settlement && (
              <p className="mt-2 text-[11px] text-chalk/35">
                Graded {etStamp(settlement.settled_at)}
              </p>
            )}
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-placard text-chalk/40">
              CLV at settlement
            </p>
            <p className="mt-2 text-lg">
              <ClvValue
                measure={settlement?.clv_pct == null ? null : relative(settlement.clv_pct)}
              />
            </p>
            <p className="mt-1.5 text-[11px] text-chalk/35">
              relative to the price bet
            </p>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-placard text-chalk/40">
              CLV live
            </p>
            <p className="mt-2 text-lg">
              <ClvValue
                measure={liveClv?.clv_pct_live == null ? null : absolute(liveClv.clv_pct_live)}
              />
            </p>
            <p className="mt-1.5 text-[11px] text-chalk/35">
              {liveClv?.latest_is_closing
                ? "against the closing snapshot"
                : "against the latest snapshot"}
            </p>
          </div>

          <Figure
            label="Closing / bet probability"
            value={
              settlement
                ? `${formatProbability(settlement.closing_prob, 2)} / ${formatProbability(settlement.bet_prob, 2)}`
                : "—"
            }
            sub={`Side: ${humanize(pick.side)}`}
          />
        </div>
        <ClvUnitsNote />
      </section>

      <Link
        href="/archive"
        className="text-[11px] uppercase tracking-placard text-chalk/45 no-underline hover:text-floodlight"
      >
        ← Back to archive
      </Link>
    </>
  );
}
