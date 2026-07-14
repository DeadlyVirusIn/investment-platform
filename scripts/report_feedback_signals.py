"""M5A — print a demand-validation report from user_feedback_signal.

Safe internal ops tool (NOT a public API). Output is anonymized: no emails, no
raw user_id, no session tokens; free-text samples are length- and count-capped.

Usage:
  python scripts/report_feedback_signals.py [--days N] [--json]
  make feedback-report   |   make feedback-report-json   |   make feedback-report-7d
"""

from __future__ import annotations

import argparse
import json

from apps.api.src.api.feedback_report import build_report
from apps.api.src.db import SessionLocal


def main() -> None:
    ap = argparse.ArgumentParser(description="ArthOS demand-validation report")
    ap.add_argument("--days", type=int, default=None, help="only signals from the last N days")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    with SessionLocal() as s:
        rep = build_report(s, days=args.days)

    if args.json:
        print(json.dumps(rep, indent=2, default=str))
        return

    print("=== ArthOS — demand-validation report ===")
    if args.days:
        print(f"window: last {args.days} days")
    print(f"total signals: {rep['total_signals']}")
    if rep["total_signals"] == 0:
        print("(no signals yet)")
        return

    print(f"authenticated users: {rep['authenticated_users']}")
    print(f"anonymous contexts:  {rep['anonymous_contexts']}")
    print(f"useful: {rep['useful']}  not useful: {rep['not_useful']}  ratio: {rep['useful_ratio']}")
    print(f"would use again: {rep['would_use_again']}  not yet: {rep['would_not_use_again']}  ratio: {rep['would_use_again_ratio']}")
    print(f"beta interest: {rep['beta_interest']}")
    print(f"feedback texts: {rep['feedback_text_count']}")

    print("by surface:")
    for k, v in rep["by_surface"].items():
        print(f"  {k}: {v}")
    print("by type:")
    for k, v in rep["by_type"].items():
        print(f"  {k}: {v}")

    if rep["text_samples"]:
        print("sample feedback (anonymized, capped):")
        for sample in rep["text_samples"]:
            print(f"  - {sample}")

    if rep["trend_7d"]:
        print("last 7 days:")
        for d in rep["trend_7d"]:
            print(f"  {d['day']}: {d['count']}")


if __name__ == "__main__":
    main()
