"""Controlled strategy evaluation layer (Phase 11H).

Read-only, paper-only, deterministic rule-based scoring (0-100) of the
historical observations produced by Phase 11G. NEVER recommends a
trade. NEVER ranks one strategy as "best". NEVER uses ML or learned
weights. NEVER opens a paper trade.

Score components (frozen v1, locked module constants):
  * Liquidity quality          25 pts
  * Risk/reward quality        25 pts
  * Volatility context         20 pts
  * Structure quality          20 pts
  * Model/data penalties      up to -20 pts

Total clamped to [0, 100]. Component breakdown + per-criterion
explanation always returned alongside the score so operators can
audit how each input shaped the result.
"""
