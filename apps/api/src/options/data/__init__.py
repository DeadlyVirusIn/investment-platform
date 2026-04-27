"""Options data layer (Phase 11C).

Liquidity filters + chain-snapshot orchestrator.
Pure-fn modules + one orchestrator that performs INSERT-only writes.
NEVER imports V2 / equity / strategy / execution code.
"""
