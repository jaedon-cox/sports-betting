import { BankrollProvider } from "@/components/bankroll/bankroll-context";
import { GameBlock } from "@/components/picks/game-block";
import { ScopeToggle } from "@/components/picks/scope-toggle";
import { SlateSummary } from "@/components/picks/slate-summary";
import { EmptyState, PageTitle, Placard } from "@/components/ui/primitives";
import { getSlate } from "@/lib/data/todays-picks";
import {
  applyScope,
  gameCloseState,
  groupByGame,
  indexClv,
  slateState,
  summarize,
  type SlateScope,
} from "@/lib/slate";
import { etDayLabel } from "@/lib/time";

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

export default async function TodaysPicksPage({
  searchParams,
}: {
  searchParams: { scope?: string };
}) {
  const { data } = await getSlate();
  const scope: SlateScope =
    searchParams.scope === "recommended" ? "recommended" : "all";

  const forToday = data.picks.filter((p) => p.game_date === data.today);
  const state = slateState({
    today: data.today,
    gamesToday: data.gamesToday,
    run: data.run,
    picksForToday: forToday.length,
  });

  if (state !== "ready") {
    return (
      <>
        <PageTitle kicker={etDayLabel(data.today)}>Today&rsquo;s board</PageTitle>
        {state === "off_day" ? (
          <EmptyState
            title="No games today"
            body="The schedule is empty, so there is nothing to price. The board returns with the next slate."
          />
        ) : (
          <EmptyState
            title="Picks pending"
            body={
              <>
                Today&rsquo;s games are on the schedule but the confirmed run has
                not published yet. Picks appear the moment the pipeline commits
                the slate — lineups and the closing-side prices are locked in one
                transaction, so a half-finished board is never shown.
              </>
            }
          />
        )}
      </>
    );
  }

  const shown = applyScope(forToday, scope);
  const totals = summarize(forToday, shown);
  const groups = groupByGame(shown);
  const clv = indexClv(data.clv);

  return (
    <BankrollProvider>
      <PageTitle kicker={etDayLabel(data.today)}>Today&rsquo;s board</PageTitle>
      <SlateSummary totals={totals} run={data.run} />

      <div className="mb-6">
        <ScopeToggle
          scope={scope}
          nEvaluated={totals.nEvaluated}
          nRecommended={totals.nRecommended}
        />
        <p className="mt-2 max-w-2xl text-[11px] leading-relaxed text-chalk/35">
          Every game the model prices is listed, whether or not it cleared the
          bet threshold. Closing-line value is tracked on all of them — a
          declined game with a good line is still evidence about the model.
        </p>
      </div>

      <Placard>
        {groups.length} game{groups.length === 1 ? "" : "s"}
      </Placard>

      {groups.length === 0 ? (
        <EmptyState
          title="Nothing recommended"
          body="No game on today's slate cleared the bet threshold. Switch to all-evaluated to see the full board."
        />
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <GameBlock
              key={group.gameId}
              group={group}
              close={gameCloseState(group, clv)}
            />
          ))}
        </div>
      )}
    </BankrollProvider>
  );
}
