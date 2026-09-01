/**
 * The generic parameter for supabase-js, assembled from lib/types/rows.ts so
 * there is exactly one transcription of the schema. Binding the client to it
 * is what keeps `any` out of the data layer: `.from('v_todays_picks')` is
 * typed, and a column removed from a view fails the build at the call site.
 *
 * Only relations the frontend actually reads appear here. Everything the
 * pipeline writes is deliberately absent — the frontend has no write path to
 * it (§5: writes are service-role only, plus a user's own user_settings).
 */
import type {
  CalibrationBucketRow,
  ClvTrendRow,
  LineSnapshotRow,
  MarketDefRow,
  ModelRunRow,
  PickArchiveRow,
  PickClvLiveRow,
  PickSettlementRow,
  RecordSummaryRow,
  RoiCurveRow,
  TodaysPickRow,
  UserSettingsRow,
} from "./rows";

/** A table the frontend may only SELECT: the Insert/Update surface is empty. */
type ReadOnlyTable<Row> = {
  Row: Row;
  Insert: Record<string, never>;
  Update: Record<string, never>;
  Relationships: [];
};

/** A view. Non-updatable views carry no Insert/Update at all. */
type ReadOnlyView<Row> = {
  Row: Row;
  Relationships: [];
};

/** games, read only for the count that distinguishes an off-day from a pending slate. */
type GameRow = {
  id: number;
  sport: string;
  external_game_id: string;
  game_date: string;
  start_time_utc: string | null;
  status: string;
}

export type Database = {
  public: {
    Tables: {
      calibration_buckets: ReadOnlyTable<CalibrationBucketRow>;
      line_snapshots: ReadOnlyTable<LineSnapshotRow>;
      pick_settlements: ReadOnlyTable<PickSettlementRow>;
      model_runs: ReadOnlyTable<ModelRunRow>;
      markets: ReadOnlyTable<MarketDefRow>;
      games: ReadOnlyTable<GameRow>;
      // The one user-writable relation (db/policies/003_user_owned_rls.sql).
      user_settings: {
        Row: UserSettingsRow;
        Insert: Pick<UserSettingsRow, "user_id"> &
          Partial<Omit<UserSettingsRow, "user_id">>;
        Update: Partial<Omit<UserSettingsRow, "user_id">>;
        Relationships: [];
      };
    };
    Views: {
      v_todays_picks: ReadOnlyView<TodaysPickRow>;
      v_pick_archive: ReadOnlyView<PickArchiveRow>;
      v_pick_clv_live: ReadOnlyView<PickClvLiveRow>;
      record_summary: ReadOnlyView<RecordSummaryRow>;
      mv_clv_trend: ReadOnlyView<ClvTrendRow>;
      mv_roi_curve: ReadOnlyView<RoiCurveRow>;
    };
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
}
