"""Engine ↔ ML shadow disagreement analysis.

Joins engine actions with ML actions on the same decision. Surfaces the
most valuable questions:
  * when engine fires but ML avoids, is the trade worse than average?
  * when engine skips but ML would accept, are we missing winners?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class DisagreementBucket:
    name: str
    count: int
    mean_return: float
    hit_rate: float
    top_reason_codes: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "mean_return": round(self.mean_return, 6),
            "hit_rate":    round(self.hit_rate, 4),
            "top_reason_codes": list(self.top_reason_codes),
        }


@dataclass
class DisagreementReport:
    total: int
    agree: int
    disagree: int
    agreement_rate: float
    buckets: list[DisagreementBucket] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "agree": self.agree,
            "disagree": self.disagree,
            "agreement_rate": round(self.agreement_rate, 4),
            "buckets": [b.to_dict() for b in self.buckets],
        }


def compute_disagreements(
    df: pd.DataFrame,
    *,
    engine_action_col: str = "action",
    ml_action_col: str = "ml_action",
    engine_conf_col: str = "engine_confidence",
    ml_conf_col: str = "ml_confidence",
    return_col: str = "fwd_ret_5d",
    reason_codes_col: str = "ml_reason_codes",
) -> DisagreementReport:
    if df.empty:
        return DisagreementReport(
            total=0, agree=0, disagree=0, agreement_rate=0.0,
        )

    w = df.copy()
    for c in (engine_action_col, ml_action_col):
        if c not in w.columns:
            w[c] = None
    if return_col not in w.columns:
        w[return_col] = np.nan

    engine_accept = w[engine_action_col].isin(["enter_long", "accept"])
    ml_accept = w[ml_action_col].isin(["accept"])
    ml_avoid  = w[ml_action_col].isin(["avoid"])
    ml_reduce = w[ml_action_col].isin(["reduce"])

    agree_mask = (engine_accept & ml_accept) | ((~engine_accept) & (~ml_accept))
    agree = int(agree_mask.sum())
    total = int(len(w))
    disagree = total - agree

    buckets: list[DisagreementBucket] = []
    buckets.append(_bucket(
        "engine_accept_ml_avoid",
        w[engine_accept & ml_avoid], return_col, reason_codes_col,
    ))
    buckets.append(_bucket(
        "engine_skip_ml_accept",
        w[(~engine_accept) & ml_accept], return_col, reason_codes_col,
    ))
    buckets.append(_bucket(
        "engine_high_ml_low_conf",
        w[(w[engine_conf_col].fillna(0) >= 0.6)
          & (w[ml_conf_col].fillna(0) < 0.3)],
        return_col, reason_codes_col,
    ))
    buckets.append(_bucket(
        "engine_low_ml_high_conf",
        w[(w[engine_conf_col].fillna(0) < 0.3)
          & (w[ml_conf_col].fillna(0) >= 0.6)],
        return_col, reason_codes_col,
    ))
    buckets.append(_bucket(
        "engine_accept_ml_reduce",
        w[engine_accept & ml_reduce], return_col, reason_codes_col,
    ))

    return DisagreementReport(
        total=total,
        agree=agree,
        disagree=disagree,
        agreement_rate=(agree / total) if total else 0.0,
        buckets=buckets,
    )


# ---------------------------------------------------------------------------
def _bucket(
    name: str, sub: pd.DataFrame,
    return_col: str, reason_codes_col: str,
) -> DisagreementBucket:
    n = int(len(sub))
    if n == 0:
        return DisagreementBucket(
            name=name, count=0, mean_return=0.0, hit_rate=0.0,
        )
    rets = pd.to_numeric(sub[return_col], errors="coerce").dropna()
    mean_r = float(rets.mean()) if not rets.empty else 0.0
    hit = float((rets > 0).mean()) if not rets.empty else 0.0
    codes: dict[str, int] = {}
    if reason_codes_col in sub.columns:
        for rc in sub[reason_codes_col].dropna():
            if isinstance(rc, list):
                for c in rc:
                    codes[str(c)] = codes.get(str(c), 0) + 1
            elif isinstance(rc, str):
                codes[rc] = codes.get(rc, 0) + 1
    top = sorted(codes.items(), key=lambda kv: -kv[1])[:5]
    return DisagreementBucket(
        name=name, count=n, mean_return=mean_r,
        hit_rate=hit, top_reason_codes=top,
    )
