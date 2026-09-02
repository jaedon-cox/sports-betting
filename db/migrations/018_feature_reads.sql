-- The three reads features/source.py makes, one named function each.
-- Same rationale as 012: PostgrestClient exposes no filtered select, so
-- every read is a function over /rpc rather than a query builder.
-- Grants are in db/policies/005_feature_reads.sql.
--
-- ALL THREE RETURN PER-GAME ROWS, NOT AGGREGATES. The weighting is an
-- EWMA over game_date (model doc §10.1) with numerator and denominator
-- weighted separately (§4.6), and that is model logic -- it belongs in
-- Python next to core/recency.py where it is unit-testable, not spread
-- across a SQL window function. These functions do exactly two things:
-- restrict to the entities asked for, and enforce the as-of cut.
--
-- THE AS-OF CUT IS `game_date < p_as_of`, STRICTLY LESS THAN.
-- A game played on the slate date has not finished when a pick is
-- locked at T-45min, so including it would price tonight's game partly
-- on tonight's result -- the exact leakage CLAUDE.md rule 4 exists to
-- prevent, and it would inflate backtest CLV without touching live CLV,
-- making the backtest silently optimistic. `<=` here would be a
-- one-character correctness bug with no visible symptom.
--
-- p_from bounds the window rather than scanning all history: an EWMA
-- with a season-scale half-life gets no measurable weight from three
-- years ago, and the index is (entity, game_date DESC).

CREATE OR REPLACE FUNCTION fn_pitcher_game_form(
    p_player_ids TEXT[],
    p_from       DATE,
    p_as_of      DATE
) RETURNS TABLE (
    player_id      TEXT,
    game_date      DATE,
    throws         TEXT,
    is_start       BOOLEAN,
    pitches        INTEGER,
    csw            INTEGER,
    batters_faced  INTEGER,
    outs           INTEGER,
    strikeouts     INTEGER,
    walks          INTEGER,
    hit_by_pitch   INTEGER,
    home_runs      INTEGER,
    ground_balls   INTEGER,
    fly_balls      INTEGER,
    line_drives    INTEGER,
    popups         INTEGER,
    siera          NUMERIC
)
LANGUAGE sql STABLE AS $$
    SELECT s.player_id, s.game_date, s.throws, s.is_start,
           s.pitches, s.csw, s.batters_faced, s.outs,
           s.strikeouts, s.walks, s.hit_by_pitch, s.home_runs,
           s.ground_balls, s.fly_balls, s.line_drives, s.popups, s.siera
    FROM pitcher_game_stats s
    WHERE s.player_id = ANY (p_player_ids)
      AND s.game_date >= p_from
      AND s.game_date <  p_as_of
    ORDER BY s.player_id, s.game_date;
$$;

-- Relief appearances only (is_start = FALSE), pre-aggregated to one row
-- per (club, date) because a bullpen is a unit, not a set of arms: the
-- feature is the club's relief corps quality and workload, and which
-- individual threw is not carried into features/bullpen.py.
--
-- This is the one place aggregation happens in SQL, and only because
-- the grain being summed is *within* a single game_date -- summing
-- three relievers' walks from one night is not a weighted rate and
-- cannot become a mean of means. The cross-date EWMA still happens in
-- Python.
CREATE OR REPLACE FUNCTION fn_bullpen_game_form(
    p_teams  TEXT[],
    p_from   DATE,
    p_as_of  DATE
) RETURNS TABLE (
    pitching_team  TEXT,
    game_date      DATE,
    appearances    BIGINT,
    pitches        BIGINT,
    outs           BIGINT,
    batters_faced  BIGINT,
    strikeouts     BIGINT,
    walks          BIGINT,
    hit_by_pitch   BIGINT,
    home_runs      BIGINT,
    ground_balls   BIGINT,
    fly_balls      BIGINT,
    line_drives    BIGINT,
    popups         BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT s.pitching_team, s.game_date,
           COUNT(*)                AS appearances,
           SUM(s.pitches)          AS pitches,
           SUM(s.outs)             AS outs,
           SUM(s.batters_faced)    AS batters_faced,
           SUM(s.strikeouts)       AS strikeouts,
           SUM(s.walks)            AS walks,
           SUM(s.hit_by_pitch)     AS hit_by_pitch,
           SUM(s.home_runs)        AS home_runs,
           SUM(s.ground_balls)     AS ground_balls,
           SUM(s.fly_balls)        AS fly_balls,
           SUM(s.line_drives)      AS line_drives,
           SUM(s.popups)           AS popups
    FROM pitcher_game_stats s
    WHERE s.pitching_team = ANY (p_teams)
      AND NOT s.is_start
      AND s.game_date >= p_from
      AND s.game_date <  p_as_of
    GROUP BY s.pitching_team, s.game_date
    ORDER BY s.pitching_team, s.game_date;
$$;

-- Club batting, still split by the hand faced: features/offense.py
-- resolves `xwoba_vs_opp_hand` against tonight's opposing starter, so
-- collapsing the split here would destroy the only thing the column is
-- for.
CREATE OR REPLACE FUNCTION fn_team_batting_form(
    p_teams  TEXT[],
    p_from   DATE,
    p_as_of  DATE
) RETURNS TABLE (
    batting_team       TEXT,
    game_date          DATE,
    opp_hand           TEXT,
    plate_appearances  INTEGER,
    xwoba_sum          NUMERIC
)
LANGUAGE sql STABLE AS $$
    SELECT b.batting_team, b.game_date, b.opp_hand, b.plate_appearances, b.xwoba_sum
    FROM team_batting_game_stats b
    WHERE b.batting_team = ANY (p_teams)
      AND b.game_date >= p_from
      AND b.game_date <  p_as_of
    ORDER BY b.batting_team, b.game_date;
$$;

-- ---------------------------------------------------------------------
-- fn_injury_status_asof — the newest non-active row per player at
-- `p_as_of`, for one club's 40-man.
--
-- Unlike the three functions above this IS a point-in-time snapshot
-- read, because IL status genuinely moves. The `DISTINCT ON ... ORDER BY
-- captured_at_utc DESC` shape is backend doc §3.2's.
--
-- READ THE ABSENCE RULE BEFORE USING THIS. jobs/roster_pull.py writes a
-- row only for players who are NOT active, to keep ~2M rows a season out
-- of a 500 MB tier. So "no row" means available -- but it also means
-- "never pulled". A player returning to active writes nothing, so the
-- newest row for him stays his old IL row forever. Callers must
-- therefore bound the lookback (p_since) to roughly one pull cadence:
-- a stale row older than the club's last sweep is a player who has
-- since been reinstated, not a player still hurt.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_injury_status_asof(
    p_team_ids BIGINT[],
    p_since    TIMESTAMPTZ,
    p_as_of    TIMESTAMPTZ
) RETURNS TABLE (
    player_id  TEXT,
    team_id    BIGINT,
    status     TEXT
)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (i.player_id)
           i.player_id, i.team_id, i.status
    FROM injury_snapshots i
    WHERE i.team_id = ANY (p_team_ids)
      AND i.captured_at_utc >  p_since
      AND i.captured_at_utc <= p_as_of
    ORDER BY i.player_id, i.captured_at_utc DESC;
$$;

-- ---------------------------------------------------------------------
-- fn_weather_asof — the newest forecast per game at `p_as_of`.
--
-- Forecasts only; `weather_snapshots.is_forecast` is structurally always
-- true (jobs/weather_pull.py), and model doc §3.7 is explicit that a
-- realized observation is leakage that inflates backtest CLV. The filter
-- is kept anyway so that stays true if an observed row is ever written.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_weather_asof(
    p_game_ids BIGINT[],
    p_as_of    TIMESTAMPTZ
) RETURNS TABLE (
    game_id       BIGINT,
    temp_f        NUMERIC,
    wind_mph      NUMERIC,
    wind_dir_deg  SMALLINT,
    precip_pct    NUMERIC
)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (w.game_id)
           w.game_id, w.temp_f, w.wind_mph, w.wind_dir_deg, w.precip_pct
    FROM weather_snapshots w
    WHERE w.game_id = ANY (p_game_ids)
      AND w.is_forecast
      AND w.captured_at_utc <= p_as_of
    ORDER BY w.game_id, w.captured_at_utc DESC;
$$;
