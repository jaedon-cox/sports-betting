import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import { CACHE_TAGS } from "@/lib/cache";
import type { MarketDefRow } from "@/lib/types/rows";
import { fixture, live, type Sourced, unwrap } from "./source";

/**
 * The set of markets is read from the database, never hard-coded (rule 7):
 * adding a player prop is an INSERT into `markets`, and the archive filter
 * picks it up with no frontend change.
 */
export async function getMarkets(): Promise<Sourced<MarketDefRow[]>> {
  if (!isSupabaseConfigured) {
    const created = "2026-01-01T00:00:00.000Z";
    return fixture([
      { key: "moneyline", display_name: "Moneyline", required_dims: 2, sides: ["home", "away"], devig_method: "power", created_at: created },
      { key: "total", display_name: "Run Total", required_dims: 2, sides: ["over", "under"], devig_method: "power", created_at: created },
      { key: "spread", display_name: "Run Line", required_dims: 2, sides: ["home", "away"], devig_method: "power", created_at: created },
    ]);
  }
  const supabase = createServerSupabase([CACHE_TAGS.reference]);
  return live(
    unwrap(
      await supabase.from("markets").select("*").order("key", { ascending: true }),
      "markets",
    ),
  );
}
