"""Backtest / replay package.

Real-paper-parity replay: runs the LIVE recommendation engine
(compute_for_asset) and paper-execution path (submit_trade) over historical
decision dates using the bias-guarded as_of seams. Distinct from
``apps.api.src.ml.replay`` (which is a rules-mirror + ML-label subsystem).
"""
