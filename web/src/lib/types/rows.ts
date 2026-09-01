/**
 * Row shapes for every relation the frontend reads, transcribed column-for-
 * column from db/views/*.sql and db/migrations/*.sql. These are the only
 * place the frontend asserts what the database looks like: fixtures are typed
 * against them, and the supabase-js client is generically bound to them, so a
 * schema drift surfaces as a type error rather than a runtime undefined.
 *
 * Type mapping: BIGINT/INTEGER/NUMERIC -> number (PostgREST emits all of them
 * as JSON numbers), DATE/TIMESTAMPTZ/TEXT/UUID -> string, BOOLEAN -> boolean.
 * Nullability mirrors the DDL exactly, including columns that are non-null in
 * the base table but nullable through a LEFT JOIN.
 */

/** Probability in [0,1]. NUMERIC(6,5) in the schema. */
export type Probability = number;

/** picks.side, constrained by markets.sides via fn_validate_pick(). */
export type Side = "home" | "away" | "over" | "under";

/** games.status */
export type GameStatus =
  | "scheduled"
  | "in_progress"
  | "final"
  | "postponed"
  | "cancelled";

/** pick_settlements.outcome */
export type Outcome = "win" | "loss" | "push" | "void";

/** db/views/v_todays_picks.sql — flat, one row per pick; group by game_id. */
export type TodaysPickRow = {
  id: number;
  game_id: number;
  game_date: string;
  sport: string;
  market: string;
  side: Side;
  line: number | null;
  player_id: string | null;
  stat_type: string | null;
  raw_model_prob: Probability;
  model_prob: Probability;
  market_fair_prob: Probability | null;
  market_odds_american: number | null;
  book: string;
  edge_pct: number | null;
  recommended: boolean;
  kelly_stake_fraction: number;
  pick_locked_at: string;
  run_date: string;
  pass_type: string;
  model_version_id: number;
  external_game_id: string;
  start_time_utc: string | null;
  game_status: GameStatus;
  park_name: string | null;
  home_team_code: string;
  home_team_name: string;
  away_team_code: string;
  away_team_name: string;
}

/** db/views/v_pick_archive.sql — settlement columns are LEFT JOINed. */
export type PickArchiveRow = {
  id: number;
  game_id: number;
  game_date: string;
  sport: string;
  market: string;
  side: Side;
  line: number | null;
  player_id: string | null;
  stat_type: string | null;
  model_prob: Probability;
  market_fair_prob: Probability | null;
  market_odds_american: number | null;
  book: string;
  edge_pct: number | null;
  recommended: boolean;
  kelly_stake_fraction: number;
  pick_locked_at: string;
  external_game_id: string;
  start_time_utc: string | null;
  game_status: GameStatus;
  home_team_code: string;
  away_team_code: string;
  outcome: Outcome | null;
  clv_pct: number | null;
  settled_at: string | null;
}

/**
 * db/views/v_pick_clv_live.sql. NOTE clv_pct_live is an ABSOLUTE probability
 * difference, unlike PickArchiveRow.clv_pct which is RELATIVE. See lib/clv.ts.
 */
export type PickClvLiveRow = {
  pick_id: number;
  game_id: number;
  sport: string;
  market: string;
  side: Side;
  line: number | null;
  book: string;
  locked_fair_prob: Probability | null;
  locked_odds_american: number | null;
  pick_locked_at: string;
  latest_odds_american: number | null;
  latest_fair_prob: Probability | null;
  latest_captured_at: string | null;
  latest_is_closing: boolean | null;
  clv_pct_live: number | null;
}

/** db/views/record_summary.sql (materialized). market='blended' is the all-markets row. */
export type RecordSummaryRow = {
  rollup_date: string;
  sport: string;
  market: string;
  n_evaluated: number;
  n_recommended: number;
  wins: number;
  losses: number;
  pushes: number;
  units_staked: number;
  units_won: number;
  roi_pct: number | null;
  avg_clv_pct: number | null;
  clv_positive_rate: number | null;
  avg_edge_pct: number | null;
}

/** db/views/mv_clv_trend.sql (materialized). */
export type ClvTrendRow = {
  rollup_date: string;
  sport: string;
  market: string;
  n_evaluated: number;
  avg_clv_pct: number | null;
  cum_n_evaluated: number;
  cum_avg_clv_pct: number | null;
  cum_clv_positive_rate: number | null;
}

/** db/views/mv_roi_curve.sql (materialized). */
export type RoiCurveRow = {
  rollup_date: string;
  sport: string;
  market: string;
  n_recommended: number;
  units_staked: number;
  units_won: number;
  roi_pct: number | null;
  cum_n_recommended: number;
  cum_units_staked: number;
  cum_units_won: number;
  cum_roi_pct: number | null;
}

/** db/views/calibration_buckets.sql — a physical table, not a matview. */
export type CalibrationBucketRow = {
  rollup_date: string;
  sport: string;
  market: string;
  predicted_bucket: number;
  method_version: string;
  n: number;
  avg_predicted_prob: Probability | null;
  actual_win_rate: Probability | null;
  created_at: string;
  updated_at: string;
}

/** db/migrations/004_line_history_and_settlement.sql */
export type LineSnapshotRow = {
  id: number;
  game_id: number;
  sport: string;
  market: string;
  side: Side;
  line: number | null;
  price_american: number;
  implied_prob_devigged: Probability | null;
  devig_method: string | null;
  captured_at_utc: string;
  source: string;
  is_closing: boolean;
}

/** db/migrations/004_line_history_and_settlement.sql */
export type PickSettlementRow = {
  pick_id: number;
  outcome: Outcome;
  clv_pct: number | null;
  closing_prob: Probability | null;
  bet_prob: Probability | null;
  settled_at: string;
}

/** db/migrations/001_reference_and_versioning.sql — publish time for the banner (§4.5). */
export type ModelRunRow = {
  id: number;
  model_version_id: number;
  sport: string;
  run_date: string;
  pass_type: string;
  status: string;
  github_run_id: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * db/migrations/001_reference_and_versioning.sql. The market list is DATA, not
 * an enum in code (CLAUDE.md rule 7) — the archive's market filter is built
 * from this table so a fourth market needs no frontend change.
 */
export type MarketDefRow = {
  key: string;
  display_name: string;
  required_dims: number;
  sides: string[];
  devig_method: string;
  created_at: string;
};

/** db/migrations/006_users_and_auth.sql — RLS-scoped to auth.uid(). */
export type UserSettingsRow = {
  user_id: string;
  bankroll_usd: number;
  notify_email: boolean;
  created_at: string;
  updated_at: string;
}
