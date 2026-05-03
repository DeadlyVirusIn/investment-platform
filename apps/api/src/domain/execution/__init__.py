"""Execution intelligence — post-signal sizing + regime gating.

Pivot after meta-label abandonment (2026-04-21): trade-filtering proved
economically useless (AUC-without-utility divergence on deterministic
primary). Focus shifts to HOW trades are executed, not WHICH trades.

Architecture (all pure functions, no DB coupling):

    primary_signal  ->  regime classifier  ->  position sizer  ->  gated size

Nothing here modifies signal generation or ranking. Post-processing only.
"""
