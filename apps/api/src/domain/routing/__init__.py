"""Regime-aware signal routing — Phase B3 (2026-04-21).

Rule-based layer that selects WHICH signal streams to execute given the
current market regime. Derived from Phase B2 observational evidence:

  - low_vol   -> both model + behavioral (behavioral outperformed)
  - trend_up  -> model only (behavioral adds noise)
  - sideways  -> both, but reduce exposure 0.5x (all negative in sample)
  - high_vol / unknown -> fallback model only

No tuning. No weighting. No ML. Pure if/else routing.
"""
