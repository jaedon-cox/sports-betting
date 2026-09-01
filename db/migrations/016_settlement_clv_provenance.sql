-- pick_settlements.clv_pct must carry the two probabilities it was
-- derived from.
--
-- 004 constrains clv_pct's RANGE (via the BETWEEN 0 AND 1 checks on
-- closing_prob and bet_prob) but never its PROVENANCE: a row storing
-- clv_pct with either input NULL is accepted today. That row is
-- permanently unauditable — pick_settlements is insert-once (§3.1), so
-- nothing can go back and supply the missing leg, and CLV is the gate
-- metric this whole system is judged on. Storing the derived number
-- without the inputs is worse than storing neither.
--
-- Why this exists as a CHECK and not only as the guard in
-- src/sbm/store/facts.py::SettlementRow: the Python guard binds one
-- writer, and `store/` is not the only path to this table — the
-- service-role key can INSERT directly and bypasses RLS entirely (§5).
-- A constraint binds every writer forever. The guard stays as the
-- earlier, better-worded failure for the same rule, which is exactly
-- what LineSnapshotRow's guard already does for 004's devig pairing.
--
-- Honest note on how reachable this is: it is NOT reachable from Job F
-- today. job_f_settlement/outcomes.py::_clv returns None whenever either
-- leg is missing, and _settle_one passes the two probs and the CLV
-- together, so the live path cannot construct a violating row. This
-- constraint is a boundary contract for the next writer, not a fix for a
-- live bug — unlike 013, which repaired a gap that made every priced
-- pick unpublishable. Recording the distinction because the two were
-- briefly conflated in review.
--
-- The reverse pairing is deliberately legal: bet_prob and/or
-- closing_prob present with clv_pct NULL is the normal shape for a
-- postponed game or a missed closing sweep, which fn_unsettled_picks
-- returns as NULL legs and Job F settles as a void row with an outcome
-- and no number.

ALTER TABLE pick_settlements
    ADD CONSTRAINT ck_pick_settlements_clv_provenance
    CHECK (clv_pct IS NULL OR (bet_prob IS NOT NULL AND closing_prob IS NOT NULL));
