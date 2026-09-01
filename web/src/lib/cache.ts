/**
 * Cache surface for the publish handshake (§2.3, §5): the pipeline flips
 * model_runs.status to 'success' and then curls the revalidate endpoint. No
 * polling, no websockets.
 *
 * Tags are per read-surface rather than one global tag so a slate publish does
 * not throw away the settled history, which only changes after the nightly
 * settlement job.
 */
export const CACHE_TAGS = {
  /** v_todays_picks, v_pick_clv_live, model_runs — changes on every publish. */
  slate: "slate",
  /** record_summary, mv_clv_trend, mv_roi_curve, calibration_buckets. */
  record: "record",
  /** v_pick_archive and per-pick detail reads. */
  archive: "archive",
  /** markets and other lookup data — effectively static. */
  reference: "reference",
} as const;

export type CacheTag = (typeof CACHE_TAGS)[keyof typeof CACHE_TAGS];

export const ALL_CACHE_TAGS: CacheTag[] = Object.values(CACHE_TAGS);

/** Paths whose rendered output is identical for every authenticated reader. */
export const REVALIDATABLE_PATHS = ["/", "/record", "/archive"] as const;

/**
 * Backstop only. Correctness comes from the webhook; this bounds how stale the
 * board can get if a publish ever fails to call it.
 */
export const DATA_TTL_SECONDS = 900;
