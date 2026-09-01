import {
  lineSnapshotsFixture,
  pickArchiveFixture,
  settlementFixture,
} from "@/lib/fixtures/archive";
import { clvLiveFixture, todaysPicksFixture } from "@/lib/fixtures/slate";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import { CACHE_TAGS } from "@/lib/cache";
import type {
  LineSnapshotRow,
  PickArchiveRow,
  PickClvLiveRow,
  PickSettlementRow,
  TodaysPickRow,
} from "@/lib/types/rows";
import { fixture, live, type Sourced, unwrap } from "./source";

export interface PickDetail {
  pick: PickArchiveRow;
  liveClv: PickClvLiveRow | null;
  settlement: PickSettlementRow | null;
  /** Exactly two odds points exist per pick (§5) — open and close, no series. */
  open: LineSnapshotRow | null;
  close: LineSnapshotRow | null;
}

/** A today's-pick row projected onto the archive shape (same pick, fewer columns). */
function fromTodays(row: TodaysPickRow): PickArchiveRow {
  return {
    id: row.id,
    game_id: row.game_id,
    game_date: row.game_date,
    sport: row.sport,
    market: row.market,
    side: row.side,
    line: row.line,
    player_id: row.player_id,
    stat_type: row.stat_type,
    model_prob: row.model_prob,
    market_fair_prob: row.market_fair_prob,
    market_odds_american: row.market_odds_american,
    book: row.book,
    edge_pct: row.edge_pct,
    recommended: row.recommended,
    kelly_stake_fraction: row.kelly_stake_fraction,
    pick_locked_at: row.pick_locked_at,
    external_game_id: row.external_game_id,
    start_time_utc: row.start_time_utc,
    game_status: row.game_status,
    home_team_code: row.home_team_code,
    away_team_code: row.away_team_code,
    outcome: null,
    clv_pct: null,
    settled_at: null,
  };
}

function snapshotsFromLive(row: PickClvLiveRow): {
  open: LineSnapshotRow | null;
  close: LineSnapshotRow | null;
} {
  const base = {
    game_id: row.game_id,
    sport: row.sport,
    market: row.market,
    side: row.side,
    line: row.line,
    devig_method: "power",
    source: row.book,
  };
  const open: LineSnapshotRow | null =
    row.locked_fair_prob === null || row.locked_odds_american === null
      ? null
      : {
          ...base,
          id: row.pick_id * 10,
          price_american: row.locked_odds_american,
          implied_prob_devigged: row.locked_fair_prob,
          captured_at_utc: row.pick_locked_at,
          is_closing: false,
        };
  const close: LineSnapshotRow | null =
    row.latest_is_closing !== true || row.latest_odds_american === null
      ? null
      : {
          ...base,
          id: row.pick_id * 10 + 1,
          price_american: row.latest_odds_american,
          implied_prob_devigged: row.latest_fair_prob,
          captured_at_utc: row.latest_captured_at ?? row.pick_locked_at,
          is_closing: true,
        };
  return { open, close };
}

export async function getPickDetail(id: number): Promise<Sourced<PickDetail> | null> {
  if (!isSupabaseConfigured) {
    const archived = pickArchiveFixture().find((r) => r.id === id);
    if (archived) {
      const snaps = lineSnapshotsFixture(archived);
      return fixture({
        pick: archived,
        liveClv: null,
        settlement: settlementFixture(archived),
        open: snaps[0] ?? null,
        close: snaps[1] ?? null,
      });
    }
    const todays = todaysPicksFixture().find((r) => r.id === id);
    if (!todays) return null;
    const liveClv = clvLiveFixture().find((r) => r.pick_id === id) ?? null;
    const snaps = liveClv ? snapshotsFromLive(liveClv) : { open: null, close: null };
    return fixture({
      pick: fromTodays(todays),
      liveClv,
      settlement: null,
      open: snaps.open,
      close: snaps.close,
    });
  }

  const supabase = createServerSupabase([CACHE_TAGS.archive]);

  const pickRows = unwrap(
    await supabase.from("v_pick_archive").select("*").eq("id", id).limit(1),
    "v_pick_archive (detail)",
  );
  const pick = pickRows[0];
  if (!pick) return null;

  const liveRows = unwrap(
    await supabase.from("v_pick_clv_live").select("*").eq("pick_id", id).limit(1),
    "v_pick_clv_live (detail)",
  );
  const settlementRows = unwrap(
    await supabase.from("pick_settlements").select("*").eq("pick_id", id).limit(1),
    "pick_settlements (detail)",
  );
  // Book consistency (§5): the snapshot filter is scoped to the pick's own
  // book, so open and close are always the same book as the quoted price.
  const snapshots = unwrap(
    await supabase
      .from("line_snapshots")
      .select("*")
      .eq("game_id", pick.game_id)
      .eq("market", pick.market)
      .eq("side", pick.side)
      .eq("source", pick.book)
      .order("captured_at_utc", { ascending: true }),
    "line_snapshots (detail)",
  );

  return live({
    pick,
    liveClv: liveRows[0] ?? null,
    settlement: settlementRows[0] ?? null,
    open: snapshots.find((s) => !s.is_closing) ?? snapshots[0] ?? null,
    close: snapshots.find((s) => s.is_closing) ?? null,
  });
}
