import { ArchiveFiltersForm } from "@/components/archive/archive-filters";
import { ArchiveTable } from "@/components/archive/archive-table";
import { Pager } from "@/components/archive/pager";
import { EmptyState, PageTitle } from "@/components/ui/primitives";
import {
  decodeCursor,
  getArchivePage,
  type ArchiveFilters,
} from "@/lib/data/archive";
import { getMarkets } from "@/lib/data/markets";
import type { Outcome } from "@/lib/types/rows";

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
export const metadata = { title: "Archive" };

const OUTCOMES: readonly Outcome[] = ["win", "loss", "push", "void"];
const DATE = /^\d{4}-\d{2}-\d{2}$/;

type Params = {
  from?: string;
  to?: string;
  market?: string;
  outcome?: string;
  scope?: string;
  c?: string;
};

export default async function ArchivePage({
  searchParams,
}: {
  searchParams: Params;
}) {
  const { data: markets } = await getMarkets();
  const marketKeys = new Set(markets.map((m) => m.key));

  // Every filter is validated before it reaches a query; an unrecognised
  // value is dropped rather than passed through to PostgREST.
  const filters: ArchiveFilters = {
    from: searchParams.from && DATE.test(searchParams.from) ? searchParams.from : undefined,
    to: searchParams.to && DATE.test(searchParams.to) ? searchParams.to : undefined,
    market: searchParams.market && marketKeys.has(searchParams.market) ? searchParams.market : undefined,
    outcome: OUTCOMES.includes(searchParams.outcome as Outcome)
      ? (searchParams.outcome as Outcome)
      : undefined,
    scope: searchParams.scope === "recommended" ? "recommended" : "all",
  };

  const stack = (searchParams.c ?? "").split(",").filter(Boolean);
  const cursor = decodeCursor(stack[stack.length - 1]);
  const { data } = await getArchivePage(filters, cursor);

  const baseParams = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (typeof value === "string" && value) baseParams.set(key, value);
  }

  return (
    <>
      <PageTitle kicker="Every evaluated pick, settled and pending">Archive</PageTitle>

      <div className="mb-8">
        <ArchiveFiltersForm filters={filters} markets={markets} />
      </div>

      {data.rows.length === 0 ? (
        <EmptyState
          title="No picks match"
          body="Nothing in the record fits these filters. Widen the date range or clear the result filter."
        />
      ) : (
        <div className="panel">
          <ArchiveTable rows={data.rows} />
          <Pager
            baseParams={baseParams}
            stack={stack}
            nextCursor={data.nextCursor}
            shown={data.rows.length}
          />
        </div>
      )}

      <p className="mt-4 max-w-2xl text-[11px] leading-relaxed text-chalk/30">
        Paginated by keyset on (game date, pick id) rather than by offset, so a
        pick settled while you read never shifts a row from one page to another.
        CLV here is the settled, relative figure recorded at grading.
      </p>
    </>
  );
}
