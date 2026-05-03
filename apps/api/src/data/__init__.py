"""Data Layer (Phase DL2) — 5-layer architecture.

Layers:
  raw/         — ingestion (market, macro, positioning)
  features/    — normalized feature computation
  context/     — regime labels (production / candidate / diagnostic)
  strategy/    — read-only adapter around frozen production logic
  evaluation/  — shadow testing + ablation + audit

No new strategy logic. Infrastructure only.
"""
