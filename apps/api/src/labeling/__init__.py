"""Phase 11P.5 - paper observation labeling.

Pure-fn forward-return calculator + DB layer that persists
deterministic labels into `paper_observation_label`. NEVER trains a
model. NEVER calls an LLM. NEVER imports broker / live / execution
modules. NEVER affects strict engine behaviour.
"""
