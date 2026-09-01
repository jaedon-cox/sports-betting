import { pickArchiveFixture } from "@/lib/fixtures/archive";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import { CACHE_TAGS } from "@/lib/cache";
import type { Outcome, PickArchiveRow } from "@/lib/types/rows";
import { fixture, live, type Sourced, unwrap } from "./source";

export const PAGE_SIZE = 25;

export interface ArchiveFilters {
  from?: string;
  to?: string;
  market?: string;
  outcome?: Outcome;
  scope?: "all" | "recommended";
}

/**
 * Keyset, never OFFSET (§3.3): the cursor is the last row's
 * (game_date, id), and the predicate is the row-value comparison
 * (game_date, id) < (cursor) expressed the way PostgREST accepts it.
 * ix_picks_archive_keyset backs exactly this ordering.
 */
export interface Cursor {
  gameDate: string;
  id: number;
}

export function encodeCursor(c: Cursor): string {
  return `${c.gameDate}_${c.id}`;
}

export function decodeCursor(raw: string | undefined): Cursor | null {
  if (!raw) return null;
  const at = raw.lastIndexOf("_");
  if (at < 0) return null;
  const id = Number(raw.slice(at + 1));
  const gameDate = raw.slice(0, at);
  if (!Number.isFinite(id) || !/^\d{4}-\d{2}-\d{2}$/.test(gameDate)) return null;
  return { gameDate, id };
}

export interface ArchivePage {
  rows: PickArchiveRow[];
  nextCursor: string | null;
}

function matches(row: PickArchiveRow, f: ArchiveFilters): boolean {
  if (f.from && row.game_date < f.from) return false;
  if (f.to && row.game_date > f.to) return false;
  if (f.market && row.market !== f.market) return false;
  if (f.outcome && row.outcome !== f.outcome) return false;
  if (f.scope === "recommended" && !row.recommended) return false;
  return true;
}

export async function getArchivePage(
  filters: ArchiveFilters,
  cursor: Cursor | null,
): Promise<Sourced<ArchivePage>> {
  if (!isSupabaseConfigured) {
    const all = pickArchiveFixture()
      .filter((r) => matches(r, filters))
      .filter((r) =>
        cursor === null
          ? true
          : r.game_date < cursor.gameDate ||
            (r.game_date === cursor.gameDate && r.id < cursor.id),
      );
    const rows = all.slice(0, PAGE_SIZE);
    const last = rows[rows.length - 1];
    return fixture({
      rows,
      nextCursor:
        all.length > PAGE_SIZE && last
          ? encodeCursor({ gameDate: last.game_date, id: last.id })
          : null,
    });
  }

  const supabase = createServerSupabase([CACHE_TAGS.archive]);
  let query = supabase.from("v_pick_archive").select("*").eq("sport", "mlb");
  if (filters.from) query = query.gte("game_date", filters.from);
  if (filters.to) query = query.lte("game_date", filters.to);
  if (filters.market) query = query.eq("market", filters.market);
  if (filters.outcome) query = query.eq("outcome", filters.outcome);
  if (filters.scope === "recommended") query = query.eq("recommended", true);
  if (cursor) {
    query = query.or(
      `game_date.lt.${cursor.gameDate},and(game_date.eq.${cursor.gameDate},id.lt.${cursor.id})`,
    );
  }

  // PAGE_SIZE + 1 is the has-more probe; the extra row is never rendered.
  const rows = unwrap(
    await query
      .order("game_date", { ascending: false })
      .order("id", { ascending: false })
      .limit(PAGE_SIZE + 1),
    "v_pick_archive",
  );

  const page = rows.slice(0, PAGE_SIZE);
  const last = page[page.length - 1];
  return live({
    rows: page,
    nextCursor:
      rows.length > PAGE_SIZE && last
        ? encodeCursor({ gameDate: last.game_date, id: last.id })
        : null,
  });
}
