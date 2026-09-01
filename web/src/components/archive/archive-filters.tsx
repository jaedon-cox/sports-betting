import { humanize } from "@/lib/format";
import type { ArchiveFilters } from "@/lib/data/archive";
import type { MarketDefRow } from "@/lib/types/rows";

const OUTCOMES = ["win", "loss", "push", "void"] as const;

/**
 * A plain GET form — no client JavaScript, and the resulting URL is the whole
 * state, so a filtered view is shareable. Submitting drops the pagination
 * cursor stack automatically, which is what you want: a new filter is a new
 * first page.
 */
export function ArchiveFiltersForm({
  filters,
  markets,
}: {
  filters: ArchiveFilters;
  markets: MarketDefRow[];
}) {
  return (
    <form
      action="/archive"
      method="get"
      className="panel grid gap-4 px-4 py-4 sm:grid-cols-2 lg:grid-cols-6"
    >
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">From</span>
        <input type="date" name="from" defaultValue={filters.from} className="field num mt-1.5 py-1.5" />
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">To</span>
        <input type="date" name="to" defaultValue={filters.to} className="field num mt-1.5 py-1.5" />
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">Market</span>
        <select name="market" defaultValue={filters.market ?? ""} className="field mt-1.5 py-1.5">
          <option value="">All markets</option>
          {markets.map((m) => (
            <option key={m.key} value={m.key}>
              {m.display_name}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">Result</span>
        <select name="outcome" defaultValue={filters.outcome ?? ""} className="field mt-1.5 py-1.5">
          <option value="">Any result</option>
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {humanize(o)}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="text-[10px] uppercase tracking-placard text-chalk/40">Scope</span>
        <select name="scope" defaultValue={filters.scope ?? "all"} className="field mt-1.5 py-1.5">
          <option value="all">All evaluated</option>
          <option value="recommended">Recommended only</option>
        </select>
      </label>
      <div className="flex items-end gap-3">
        <button type="submit" className="btn-primary flex-1">
          Apply
        </button>
      </div>
    </form>
  );
}
