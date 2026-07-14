"""Purged walk-forward baseline for the LightGBM meta-labeler.

Runs the fixed-hyperparameter meta-labeler (apps/ml/training LGB_PARAMS)
per calendar-period fold using apps.ml.lab.splits purged folds over the
historical_label dataset (apps.ml.dataset.load_dataset), records per-fold
classification metrics against the constant base-rate benchmark, and —
with --registry — writes the whole run to the research_run ledger.

Skips cleanly (exit 0, clear message) when the DB, dataset, or LightGBM
runtime is absent: this script measures, it never blocks. Metrics only —
no output here is a deployability claim (gates live in apps/ml/training).

Usage (dev machine, read-only against the data):
    DATABASE_URL=... python -m scripts.research.walk_forward_baseline \
        [--seed 42] [--period Q] [--embargo-days 10] [--registry]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

DEFAULT_SEED = 42
DEFAULT_PERIOD = "Q"
DEFAULT_EMBARGO_DAYS = 10
MIN_TRAIN_ROWS = 100  # folds thinner than this are noise, not evidence
NUM_BOOST_ROUND = 300


def _skip(msg: str) -> int:
    print(f"[walk_forward_baseline] SKIP: {msg}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--period", default=DEFAULT_PERIOD,
                        help="calendar fold period (pandas alias; default Q)")
    parser.add_argument("--embargo-days", type=int, default=DEFAULT_EMBARGO_DAYS)
    parser.add_argument("--registry", action="store_true",
                        help="record the run in the research_run ledger")
    args = parser.parse_args(argv)

    if not os.environ.get("DATABASE_URL"):
        return _skip("DATABASE_URL not set — no data source")
    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:  # OSError: missing libgomp
        return _skip(f"lightgbm unavailable: {exc}")

    import numpy as np

    from apps.ml.dataset import load_dataset
    from apps.ml.lab import benchmarks as lab_benchmarks
    from apps.ml.lab import metrics as lab_metrics
    from apps.ml.lab.splits import purged_walk_forward_folds
    from apps.ml.training import LGB_PARAMS

    try:
        bundle = load_dataset()
    except Exception as exc:  # noqa: BLE001 — absent table / empty dataset / conn refused
        return _skip(f"dataset unavailable ({type(exc).__name__}: {exc})")

    df = bundle.df
    try:
        folds = purged_walk_forward_folds(
            df, date_col=bundle.group_col,
            period=args.period, embargo_days=args.embargo_days,
            min_train_rows=MIN_TRAIN_ROWS,
        )
    except ValueError as exc:
        return _skip(f"not enough history to fold ({exc})")

    params = dict(LGB_PARAMS)
    params["seed"] = args.seed
    params["deterministic"] = True

    fold_rows: list[dict] = []
    for k, (tr_idx, ev_idx) in enumerate(folds):
        X_tr = df.iloc[tr_idx][bundle.features].values
        y_tr = df.iloc[tr_idx][bundle.target].values
        X_ev = df.iloc[ev_idx][bundle.features].values
        y_ev = df.iloc[ev_idx][bundle.target].values

        model = lgb.train(
            params, lgb.Dataset(X_tr, label=y_tr),
            num_boost_round=NUM_BOOST_ROUND,
            callbacks=[lgb.log_evaluation(period=0)],
        )
        proba = np.asarray(model.predict(X_ev), dtype=float)

        fold_rows.append({
            "fold": k,
            "eval_start": str(df.iloc[ev_idx][bundle.group_col].min()),
            "eval_end": str(df.iloc[ev_idx][bundle.group_col].max()),
            "n_train": int(len(tr_idx)),
            "n_eval": int(len(ev_idx)),
            "eval_hit_rate": float(np.mean(y_ev)),
            "auc": lab_metrics.auc(y_ev, proba),
            "brier": lab_metrics.brier(y_ev, proba),
            "ece": lab_metrics.ece(y_ev, proba),
            # benchmark: constant classifier at the TRAIN base rate
            "base_rate_train": float(np.mean(y_tr)),
            "base_rate_brier": lab_benchmarks.base_rate_brier(
                y_ev, base_rate=float(np.mean(y_tr))
            ),
        })

    aucs = [f["auc"] for f in fold_rows if f["auc"] is not None]
    summary = {
        "n_folds": len(fold_rows),
        "n_rows": int(len(df)),
        "mean_auc": (float(np.mean(aucs)) if aucs else None),
        "mean_brier": float(np.mean([f["brier"] for f in fold_rows])),
        "mean_base_rate_brier": float(
            np.mean([f["base_rate_brier"] for f in fold_rows])
        ),
        "folds": fold_rows,
    }
    print(json.dumps(summary, indent=1, default=str))

    if args.registry:
        _record_registry_run(args, params, bundle, df, fold_rows, summary)
    return 0


def _record_registry_run(args, lgb_params, bundle, df, fold_rows, summary) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from apps.ml.lab.registry import (
        RegistryClient, registry_table_exists, resolve_git_sha,
    )

    engine = create_engine(os.environ["DATABASE_URL"])
    if not registry_table_exists(engine):
        print("[registry] research_run table absent on this DB "
              "(migration 109 not applied) — skipping registry record")
        return

    run_params = {
        "lgb_params": {k: v for k, v in lgb_params.items()},
        "num_boost_round": NUM_BOOST_ROUND,
        "period": args.period,
        "embargo_days": args.embargo_days,
        "min_train_rows": MIN_TRAIN_ROWS,
        "features": list(bundle.features),
        "target": bundle.target,
    }
    dates = df[bundle.group_col]
    data_manifest = {
        "table": "historical_label",
        "n_rows": int(len(df)),
        "date_min": str(dates.min()),
        "date_max": str(dates.max()),
        "hit_rate": float(df[bundle.target].mean()),
    }
    metrics = {
        "n_folds": summary["n_folds"],
        "n_rows": summary["n_rows"],
        "mean_auc": summary["mean_auc"],
        "mean_brier": summary["mean_brier"],
        "mean_base_rate_brier": summary["mean_base_rate_brier"],
        "folds": fold_rows,
    }
    with Session(engine) as session:
        client = RegistryClient(session)
        run = client.create_run(
            run_type="walk_forward",
            name=f"lgbm_meta_labeler purged WF ({args.period}, "
                 f"embargo {args.embargo_days}d)",
            params=run_params,
            git_sha=resolve_git_sha(),
            seed=args.seed,
            data_window=(dates.min(), dates.max()),
            data_manifest=data_manifest,
            split_method="purged_walk_forward",
            created_by="script:walk_forward_baseline",
        )
        client.start(run)
        client.append_metrics(run, metrics)
        client.finish(run)
        session.commit()
        print(f"[registry] recorded run {run.run_uid} (completed)")


if __name__ == "__main__":
    sys.exit(main())
