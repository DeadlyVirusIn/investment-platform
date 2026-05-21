# V2 Observation Log

Weekly review records for the 60–90 day OOS observation window
beginning **2026-04-26**.

## Files

- `template.md` — copy this for each new weekly review
- `red_flag_register.md` — running count + escalation log per red flag
- `YYYY-Www.md` — one file per ISO week (operator creates from template)

## Workflow

1. **Monday morning** (after the 00:15 UTC snapshot job has run):
   - Pull `/api/v2-promotion/state`
   - Pull `/api/v2-promotion/snapshots?weeks=16`
   - Pull `/api/v2-promotion/gates`
   - Compute OOS report via
     `apps.api.src.research.v2_oos_monitoring.fetch_and_build_weekly_report(session)`
2. **Copy** `template.md` to `YYYY-Www.md` (matching the snapshot's ISO week).
3. **Fill in** every field verbatim from the API / report — do NOT
   recompute, do NOT smooth, do NOT round.
4. **Update** `red_flag_register.md` with any flags fired this week.
5. **Commit** the new weekly file + register update to the repo
   (research note; not a code change).

## Discipline

- No editing of past weeks' files. Append-only research record.
- No skipping weeks. Even a NORMAL week with zero red flags is recorded.
- Notes section is for observation only — no action items beyond
  the bounded set in the template.

## End of window

After 60 calendar days minimum (90 days target), run the §7 ML
readiness criteria check from `V2_OBSERVATION_VALIDATION_PLAN.md`.
Outcome decisions documented in a separate end-of-window summary
file: `END_OF_WINDOW_REVIEW.md`.

## Reference

- Plan: `../V2_OBSERVATION_VALIDATION_PLAN.md`
- OOS monitoring design: `../V2_OOS_MONITORING_DESIGN.md`
- Statistical validation design: `../V2_STAT_VALIDATION_DESIGN.md`
- ML advisory design (NOT implemented): `../V2_ML_ADVISORY_DESIGN.md`
- V2 promotion-trigger design: `../V2_PROMOTION_TRIGGER_DESIGN.md`
