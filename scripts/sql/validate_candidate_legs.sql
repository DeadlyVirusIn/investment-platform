-- Phase C Stage 2A — post-generation leg validation.
--
-- Run each query separately (substitute the run_date). Proves the
-- OPTIONS_PERSIST_LEGS materialization is correct and that enabling it did
-- NOT change candidate counts or scores.
--
-- Engine-executable structures only carry legs:
--   SHORT_PUT_CREDIT_SPREAD, SHORT_CALL_CREDIT_SPREAD  → exactly 2 legs
--   IRON_CONDOR                                        → exactly 4 legs
-- Research structures carry 0 legs (by design).

-- 1) Leg-count distribution by structure (expect spreads min=max=2, IC=4).
SELECT c.rule_id,
       COUNT(*)        AS candidates,
       MIN(lc.n)       AS min_legs,
       MAX(lc.n)       AS max_legs
FROM options_strategy_candidate c
JOIN (
  SELECT candidate_id, COUNT(*) AS n
  FROM options_candidate_leg
  GROUP BY candidate_id
) lc ON lc.candidate_id = c.id
WHERE c.rule_id IN ('SHORT_PUT_CREDIT_SPREAD','SHORT_CALL_CREDIT_SPREAD','IRON_CONDOR')
  AND c.run_date = DATE '2026-06-01'   -- <<< set run_date
GROUP BY c.rule_id
ORDER BY c.rule_id;

-- 2) FAIL ROWS: engine candidates with the wrong leg count (must be EMPTY).
SELECT c.id, c.rule_id, COUNT(l.id) AS n_legs
FROM options_strategy_candidate c
JOIN options_candidate_leg l ON l.candidate_id = c.id
WHERE c.run_date = DATE '2026-06-01'   -- <<< set run_date
GROUP BY c.id, c.rule_id
HAVING (c.rule_id IN ('SHORT_PUT_CREDIT_SPREAD','SHORT_CALL_CREDIT_SPREAD') AND COUNT(l.id) <> 2)
    OR (c.rule_id = 'IRON_CONDOR' AND COUNT(l.id) <> 4);

-- 3) FAIL ROWS: duplicate roles within a candidate (must be EMPTY;
--    UNIQUE(candidate_id, role) enforces this — this is a backstop check).
SELECT candidate_id, role, COUNT(*) AS dupes
FROM options_candidate_leg
GROUP BY candidate_id, role
HAVING COUNT(*) > 1;

-- 4) FAIL ROWS: legs of one candidate priced from >1 snapshot (must be EMPTY;
--    every candidate's legs must share a single priced_as_of).
SELECT candidate_id, COUNT(DISTINCT priced_as_of) AS distinct_snapshots
FROM options_candidate_leg
GROUP BY candidate_id
HAVING COUNT(DISTINCT priced_as_of) > 1;

-- 5) INVARIANT: candidate counts + scores by structure. Run this with the
--    flag OFF (baseline) and again after enabling it for the SAME run_date.
--    The two result sets must be IDENTICAL — legs live in a separate table
--    and the candidate INSERT path is unchanged, so counts/scores cannot
--    drift.
SELECT rule_id,
       COUNT(*)                         AS candidates,
       ROUND(AVG(composite_score), 6)   AS avg_composite,
       ROUND(MIN(composite_score), 6)   AS min_composite,
       ROUND(MAX(composite_score), 6)   AS max_composite
FROM options_strategy_candidate
WHERE run_date = DATE '2026-06-01'      -- <<< set run_date
GROUP BY rule_id
ORDER BY rule_id;
