import {
  calibrationBucketsFixture,
  clvTrendFixture,
  recordSummaryFixture,
  roiCurveFixture,
} from "@/lib/fixtures/history";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createServerSupabase } from "@/lib/supabase/server";
import { CACHE_TAGS } from "@/lib/cache";
import { etDateMinusDays } from "@/lib/time";
import type {
  CalibrationBucketRow,
  ClvTrendRow,
  RecordSummaryRow,
  RoiCurveRow,
} from "@/lib/types/rows";
import { fixture, live, type Sourced, unwrap } from "./source";

/** record_summary uses the literal 'blended' sentinel, not NULL, for all-markets. */
export const BLENDED_MARKET = "blended";

export const RANGES = {
  "7d": { label: "7 days", days: 7 },
  "30d": { label: "30 days", days: 30 },
  season: { label: "Season", days: 210 },
  all: { label: "All time", days: null },
} as const;

export type RangeKey = keyof typeof RANGES;

export function parseRange(value: string | undefined): RangeKey {
  return value && value in RANGES ? (value as RangeKey) : "30d";
}

export interface RecordData {
  summary: RecordSummaryRow[];
  clvTrend: ClvTrendRow[];
  roiCurve: RoiCurveRow[];
  calibration: CalibrationBucketRow[];
  since: string | null;
}

export async function getRecord(range: RangeKey): Promise<Sourced<RecordData>> {
  const days = RANGES[range].days;
  const since = days === null ? null : etDateMinusDays(days);

  if (!isSupabaseConfigured) {
    const inRange = <T extends { rollup_date: string }>(rows: T[]) =>
      since === null ? rows : rows.filter((r) => r.rollup_date >= since);
    return fixture({
      summary: inRange(recordSummaryFixture()),
      clvTrend: inRange(clvTrendFixture()),
      roiCurve: inRange(roiCurveFixture()),
      calibration: calibrationBucketsFixture(),
      since,
    });
  }

  const supabase = createServerSupabase([CACHE_TAGS.record]);

  const rollup = <T extends { gte(column: "rollup_date", value: string): T }>(q: T): T =>
    since === null ? q : q.gte("rollup_date", since);

  const summary = unwrap(
    await rollup(supabase.from("record_summary").select("*").eq("sport", "mlb")).order(
      "rollup_date",
      { ascending: true },
    ),
    "record_summary",
  );
  const clvTrend = unwrap(
    await rollup(supabase.from("mv_clv_trend").select("*").eq("sport", "mlb")).order(
      "rollup_date",
      { ascending: true },
    ),
    "mv_clv_trend",
  );
  const roiCurve = unwrap(
    await rollup(supabase.from("mv_roi_curve").select("*").eq("sport", "mlb")).order(
      "rollup_date",
      { ascending: true },
    ),
    "mv_roi_curve",
  );
  // calibration_buckets is pinned to its latest rollup + method_version: a
  // reliability diagram is a snapshot, not a time series.
  const calibration = unwrap(
    await supabase
      .from("calibration_buckets")
      .select("*")
      .eq("sport", "mlb")
      .eq("market", BLENDED_MARKET)
      .order("rollup_date", { ascending: false })
      .order("predicted_bucket", { ascending: true })
      .limit(10),
    "calibration_buckets",
  );

  return live({ summary, clvTrend, roiCurve, calibration, since });
}
