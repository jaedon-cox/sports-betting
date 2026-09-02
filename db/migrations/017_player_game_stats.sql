-- Per-game Statcast aggregates: the feature store's grain.
--
-- WHY THESE ARE NOT SNAPSHOT TABLES, despite feeding point-in-time
-- features. Every other feature source in this schema is a *_snapshots
-- table with a captured_at_utc, because it observes a value that moves
-- (a line, a forecast, an IL status). What a pitcher did on 30 Aug does
-- not move. A per-game row is a fact, so the as-of rule collapses from
-- "the newest row captured at or before as_of" to a plain
-- `WHERE game_date < as_of` — leakage becomes structurally impossible
-- rather than a discipline every caller has to keep (CLAUDE.md rule 4).
--
-- The consequence that made this the chosen design: it is BACKFILLABLE.
-- Statcast runs to 2015, so a backtest is not limited to history
-- captured after the pipeline was switched on, which is the hard limit
-- on the line-snapshot side (backend doc §7 item 3) and would have been
-- the same limit on a nightly stat snapshot.
--
-- A fact table like the rest (§3.1), but deliberately WITHOUT the
-- reject-mutation trigger that results and pick_settlements carry, and
-- with a natural unique key instead. Those two reject a second write
-- because a restated score or a re-graded pick is a correctness
-- failure. A re-pulled game is not: Statcast revises a game for a day
-- or two after it is played, so the nightly job re-covers a trailing
-- window and the revision must be allowed to land. The writer upserts
-- with merge-duplicates (ON CONFLICT DO UPDATE), so the newest pull
-- wins and an overlapping backfill is free to re-run.
--
-- The append-only guarantee that matters here is different in kind:
-- these rows describe a completed game, so the value converges and
-- stops moving. Nothing downstream is invalidated by a correction the
-- way a rewritten pick would be.
--
-- Player ids are MLBAM, the same id space as StatsAPI probable pitchers
-- and injury_snapshots.player_id, so these join without a crosswalk.
-- That is a deliberate reason for sourcing from Savant over FanGraphs,
-- whose IDfg would have needed one.
--
-- player_id and game_pk are TEXT, matching injury_snapshots.player_id,
-- picks.player_id and games.external_game_id. They are numeric in MLB
-- and the temptation is BIGINT, but the schema settled on TEXT because
-- ids are not numeric in every sport (CLAUDE.md rule 7), and a BIGINT
-- here would silently fail to join against injury_snapshots -- which is
-- exactly the join features/source.py needs for `starter_injured`.
--
-- game_pk is deliberately NOT a REFERENCES games (id). These rows are
-- backfillable to 2015, long before any slate this system ingested, so
-- a foreign key would reject precisely the history the design exists to
-- capture.

CREATE TABLE pitcher_game_stats (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id         TEXT        NOT NULL,
    game_pk           TEXT        NOT NULL,
    game_date         DATE        NOT NULL,
    pitching_team     TEXT        NOT NULL,
    throws            TEXT        CHECK (throws IN ('L', 'R')),
    is_start          BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Counting stats only, never rates. features/ weights these across
    -- games with an EWMA (model doc §10.1), and a weighted rate must be
    -- re-derived from separately weighted numerator and denominator
    -- (§4.6) -- storing k_pct here would make the season rate a mean of
    -- means, which is a different and wrong number.
    pitches           INTEGER     NOT NULL DEFAULT 0,
    csw               INTEGER     NOT NULL DEFAULT 0,
    batters_faced     INTEGER     NOT NULL DEFAULT 0,
    outs              INTEGER     NOT NULL DEFAULT 0,
    strikeouts        INTEGER     NOT NULL DEFAULT 0,
    walks             INTEGER     NOT NULL DEFAULT 0,
    hit_by_pitch      INTEGER     NOT NULL DEFAULT 0,
    home_runs         INTEGER     NOT NULL DEFAULT 0,
    ground_balls      INTEGER     NOT NULL DEFAULT 0,
    fly_balls         INTEGER     NOT NULL DEFAULT 0,
    line_drives       INTEGER     NOT NULL DEFAULT 0,
    popups            INTEGER     NOT NULL DEFAULT 0,

    -- NULL for every row this pipeline writes today, and that is the
    -- documented v1 state, not an oversight: SIERA is a FanGraphs
    -- formula and FanGraphs answers 403. The column exists now so
    -- populating it later is a backfill rather than a migration, and so
    -- features/pitcher.py's existing xFIP fallback has something to fall
    -- back FROM. See ingest/statcast_games.py::DEFERRED.
    siera             NUMERIC,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, game_pk)
);

CREATE INDEX idx_pitcher_game_stats_asof   ON pitcher_game_stats (player_id, game_date DESC);
CREATE INDEX idx_pitcher_game_stats_team   ON pitcher_game_stats (pitching_team, game_date DESC);

-- Team batting, split by the hand of the pitcher faced, because
-- features/offense.py wants xwoba_vs_opp_hand -- a club's production
-- against the hand it will actually see tonight, not its overall line.
-- Grain is (game, club, opposing hand): a club that faces a righty
-- starter and a lefty reliever produces two rows for one game.
--
-- Summed numerator and denominator for the same EWMA reason as above:
-- xwoba_sum / plate_appearances is the rate, computed after weighting,
-- never before.
CREATE TABLE team_batting_game_stats (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_pk            TEXT        NOT NULL,
    game_date          DATE        NOT NULL,
    batting_team       TEXT        NOT NULL,
    opp_hand           TEXT        NOT NULL CHECK (opp_hand IN ('L', 'R')),
    plate_appearances  INTEGER     NOT NULL DEFAULT 0,
    xwoba_sum          NUMERIC     NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (game_pk, batting_team, opp_hand)
);

CREATE INDEX idx_team_batting_asof ON team_batting_game_stats (batting_team, game_date DESC);

-- `pitching_team` / `batting_team` are Statcast's club codes. VERIFIED
-- 2026-09-02 against a live /teams pull: all 30 are byte-identical to
-- StatsAPI's `abbreviation`, ATH and AZ included, so these join to
-- teams.code directly and no crosswalk exists or is needed.
--
-- Stored as the raw feed value anyway, not resolved to teams.id on
-- write. Two reasons: these rows backfill to seasons whose clubs are
-- not in `teams` (and one franchise has since relocated), and rewriting
-- a fact at ingest time to match a reference table means a later
-- correction to that table silently changes recorded history. If the
-- two code sets ever diverge, the crosswalk belongs in
-- features/source.py next to the reader, not here.
