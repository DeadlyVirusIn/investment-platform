"""Phase B6 — Strategy Candidate generator.

Translates raw `options_shadow_decision_log` qualifications into
strategist-grade strategy candidates with explainability metadata.

Discipline:
  * Deterministic. Same (shadow_observation, chain, feature) input
    must produce identical output.
  * Read-only against shadow_decision_log + options_chain_snapshot +
    options_feature_daily + options_strategy_bias.
  * Writes ONLY into options_strategy_candidate.
  * 1-3 candidates per accepted contract (bounded).
  * Every emission persists why_emitted + triggering_rule + 4
    *_fit_reason fields so educational surfaces can explain choices.
"""
