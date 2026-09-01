import { clvLiveFixture, fixtureGameCount, modelRunFixture, todaysPicksFixture }
  from "@/lib/fixtures/slate";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import { CACHE_TAGS } from "@/lib/cache";
import { etDate } from "@/lib/time";
import type { ModelRunRow, PickClvLiveRow, TodaysPickRow } from "@/lib/types/rows";
import { fixture, live, type Sourced, unwrap } from "./source";

export interface SlateData {
  picks: TodaysPickRow[];
  clv: PickClvLiveRow[];
  /** Latest successful confirmed run — supplies the "generated at" banner (§4.5). */
  run: ModelRunRow | null;
  gamesToday: number;
  today: string;
}

export async function getSlate(): Promise<Sourced<SlateData>> {
  const today = etDate();

  if (!isSupabaseConfigured) {
    return fixture({
      picks: todaysPicksFixture(),
      clv: clvLiveFixture(),
      run: modelRunFixture(),
      gamesToday: fixtureGameCount,
      today,
    });
  }

  const supabase = createServerSupabase([CACHE_TAGS.slate]);

  const picks = unwrap(
    await supabase
      .from("v_todays_picks")
      .select("*")
      .order("start_time_utc", { ascending: true, nullsFirst: false })
      .order("game_id", { ascending: true })
      .order("market", { ascending: true }),
    "v_todays_picks",
  );

  const runResult = await supabase
    .from("model_runs")
    .select("*")
    .eq("sport", "mlb")
    .eq("status", "success")
    .eq("pass_type", "confirmed")
    .order("run_date", { ascending: false })
    .order("updated_at", { ascending: false })
    .limit(1);
  const run = unwrap(runResult, "model_runs")[0] ?? null;

  const games = await supabase
    .from("games")
    .select("id", { count: "exact", head: true })
    .eq("sport", "mlb")
    .eq("game_date", today);
  if (games.error) {
    throw new Error(`Supabase read failed (games count): ${games.error.message}`);
  }

  const ids = picks.map((p) => p.id);
  const clv = ids.length
    ? unwrap(
        await supabase.from("v_pick_clv_live").select("*").in("pick_id", ids),
        "v_pick_clv_live",
      )
    : [];

  return live({ picks, clv, run, gamesToday: games.count ?? 0, today });
}
