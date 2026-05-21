# Phase L — EXECUTION RULES

Single canonical operating contract for Phase L implementation.
Living document. Amendments tracked with date + reasoner + rationale.

---

## SMARTEST-SCOPE-CUT TRIGGERS

Invoke the smartest-scope-cut (defer user-account + inline-trade flow to Phase 1.5; ship watch-mode-only MVP first) when ANY of:

- Day 7: pre-launch fixes incomplete
- Day 7: vocabulary not seeded with 12 signals
- Day 7: < 6 skeletons authored
- Day 14: AI-account surfaces not renderable in dev
- Day 14: forbidden-phrase enforcement not blocking PRs
- Day 21: full user trade flow not end-to-end working
- Any point: team capacity drops below 3 active contributors
- Any point: constitutional violations being silently merged

Process when invoked:
1. Decision logged here with date + reasoner + rationale
2. User-portfolio + inline-trade-flow workstreams paused
3. Phase 1.5 plan drafted for user-account portion
4. Watch-mode MVP proceeds with 4 pages (Today, AI's Portfolio, AI's Decisions, Decision Detail) + manifesto + onboarding
5. External alpha begins on watch-mode product

---

## 13 IMPLEMENTATION FREEZE RULES (locked)

1. **No scope additions.** No new features, surfaces, pages, components, signals, skeletons, or copy variants beyond Phase L.4-F freeze.

2. **No architecture changes.** No new subsystems. No new tables beyond M078–M085. No new endpoints. No new caches. No new CI rules.

3. **Cut scope before cutting constitution.** Any time the choice is "ship constitutional violation" vs "miss deadline": invoke smartest-scope-cut, document here, notify PO.

4. **Constitutional checklist on every PR.** All 30 items (see L.3 §XI) checked. Reviewer signs explicitly in PR description.

5. **No LLM in production reasoning pipeline.** Pipeline is deterministic. Skeletons + parameters + rules. No generative components in render path.

6. **Forbidden-phrase Tier A is hard block.** CI failures cannot be merged with a TODO. Cannot be allow-listed.

7. **State label mandatory on every MVP page.** Every page in `apps/web/src/pages/copilot/` mounts `<StateLabel>` at top.

8. **Truth banner priority enforced.** One banner per surface max. No exceptions.

9. **Vocabulary additions require full 6-phase workflow.** No casual signal/skeleton additions during MVP build.

10. **Daily standup mandatory.** Status, blockers, dependencies. Async OK.

11. **Friday retro mandatory.** Gate review.

12. **Smartest-scope-cut triggers must be invoked, not bypassed.**

13. **Audit trail of decisions.** Every scope change, deferred feature, or invoked rule documented here.

---

## SCOPE FREEZE — MVP

### Pages (5)
- Today
- AI's Portfolio
- AI's Decisions
- Decision Detail
- Your Portfolio

### Flow (1)
- Inline trade execution (with friction reason field)

### Vocabulary (locked counts)
- Signals: 12
- Regimes: 10
- Strategy families: 10
- Invalidation triggers: 12
- Confidence buckets: 5 (frozen)
- Decision types: 5
- Portfolio states: 7
- Truth-banner causes: 8
- State-label substates: 6 (frozen)
- Contradiction reasons: 6
- **Total: 81 entries**

### Skeletons (locked count)
- 12

### Reasoning pipeline
- 10 stages, deterministic
- Genericism: exact-string-duplicate-within-7-days only (no Jaccard)
- Memory: prior-same-name lookup only
- Audit table without `ir_json` JSONB

### Pre-launch fixes (mandatory)
- OVA-1 (`paper_equity_snapshot` immutability + source tagging via M079)
- Wrapper-RC honesty across scheduled jobs
- State-label system
- Truth-banner system
- Forbidden-phrase enforcement

### Explicitly NOT shipping in MVP
- Mobile breakpoints (Phase 1.5)
- Options surfaces (placeholder only; Phase 3)
- You-vs-AI surface (Phase 2)
- Monthly retrospective (Phase 2)
- Concept callbacks (Phase 1.5)
- Reflection journal callback on close (Phase 1.5)
- AI's view on user trades (Phase 2)
- Engine Inspection (Phase 3)
- Persona tiers (Phase 3)
- Strategy Playbooks rewrite (Phase 2)
- Free-universe trading (Phase 2)
- Synthesis subsystem (Phase 2)
- Semantic genericism / embeddings (Phase 1.5)
- 23 additional signals (Phase 1.5+)
- 18 additional skeletons (Phase 1.5+)

### NEVER shipping
- Notifications (push, email, in-app red dots)
- Social features
- Gamification (badges, streaks, levels)
- Premium tier / paywalls
- Real-brokerage integration
- AI mascot / name / personality

---

## DECISION AUDIT LOG

| date | decision | reasoner | rationale |
|---|---|---|---|
| 2026-05-17 | M083 canonical semantic locked to Option A (replay = audit-only) | PO + reviewer | Per docs/research/M083_CANONICAL_SEMANTIC.md — preserves presentation immutability without scope creep |
| 2026-05-17 | M079 migration applied to dev DB | BE | Verified via OVA-1 replay test (D1.4 milestone green) |
| 2026-05-17 | snapshot_equity_now signature changed: `source` now mandatory kwarg | BE | Truth contract enforcement at writer; no DB-default reliance |
| 2026-05-17 | Exit cycle script: `--source` flag added; fail-loud if absent | BE | Forces operator awareness on every replay invocation |

---

## CONSTITUTIONAL CHECKLIST POINTER

The 30-item checklist for every PR lives in:
`docs/research/PHASE_L_3_IMPLEMENTATION.md` §XI

(Once stood up as CI rule, the checklist runs automatically on every PR.)

---

## REFERENCES

- Phase L Constitution: `docs/research/PHASE_L_CONSTITUTION.md`
- Phase L.3 Implementation Plan: `docs/research/PHASE_L_3_IMPLEMENTATION.md`
- Phase L.3-R Reasoning Pipeline Spec: `docs/research/PHASE_L_3_R_REASONING.md`
- Phase L.3-V Vocabulary Governance Spec: `docs/research/PHASE_L_3_V_VOCABULARY.md`
- Phase L.4-F Execution Freeze: `docs/research/PHASE_L_4_F_EXECUTION_FREEZE.md`
- M083 Canonical Semantic Decision: `docs/research/M083_CANONICAL_SEMANTIC.md`
- OVA findings: `docs/research/OPERATIONAL_VITALITY_AUDIT.md`
- OOVA findings: `docs/research/OPTIONS_OPERATIONAL_VITALITY_AUDIT.md`
