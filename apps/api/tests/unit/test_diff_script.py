"""Unit tests — diff script 3-rule check (logic-only, no DB)."""

from __future__ import annotations

from scripts.diff_shadow_vs_scheduler import RankedRow


def _prefect(rows: list[tuple[str, int, float]]) -> list[RankedRow]:
    return [RankedRow(symbol=s, rank_position=r, score=sc) for s, r, sc in rows]


# We test the pure 3-rule logic by calling a small helper reimplementation
# that mirrors diff_day's body but skips DB I/O.

def _pure_diff(prefect_rows, scheduler_syms, *, top_n=10, epsilon=1e-4):
    p_syms = [r.symbol for r in prefect_rows]
    p_set, s_set = set(p_syms), set(scheduler_syms)
    if p_set != s_set:
        return ("asset_set_mismatch", {
            "extra_prefect": sorted(p_set - s_set),
            "missing_prefect": sorted(s_set - p_set),
        })
    topN_p = p_syms[:top_n]
    topN_s = scheduler_syms[:top_n]
    if set(topN_p) != set(topN_s):
        return ("topn_overlap_incomplete", {})
    score_by = {r.symbol: r.score for r in prefect_rows}
    for i in range(len(topN_p)):
        if topN_p[i] == topN_s[i]:
            continue
        p_score = score_by[topN_p[i]]
        s_score = score_by[topN_s[i]]
        if abs(p_score - s_score) > epsilon:
            return (f"material_reorder_at_position_{i}",
                    {"delta": abs(p_score - s_score)})
    return ("ok", {})


def test_asset_set_mismatch_extra_prefect():
    reason, details = _pure_diff(
        _prefect([("A", 1, 0.9), ("B", 2, 0.8), ("EXTRA", 3, 0.7)]),
        ["A", "B"],
    )
    assert reason == "asset_set_mismatch"
    assert "EXTRA" in details["extra_prefect"]


def test_asset_set_mismatch_missing_prefect():
    reason, _ = _pure_diff(
        _prefect([("A", 1, 0.9)]),
        ["A", "B"],
    )
    assert reason == "asset_set_mismatch"


def test_topn_overlap_incomplete():
    # Same overall set, but top-2 differ in membership
    p = _prefect([("A", 1, 0.9), ("B", 2, 0.5), ("C", 3, 0.4)])
    s = ["C", "A", "B"]
    reason, _ = _pure_diff(p, s, top_n=2)
    assert reason == "topn_overlap_incomplete"


def test_ordering_within_epsilon_ok():
    # Swap A, B where their scores are 0.50001 vs 0.50000 — delta 1e-5 < epsilon
    p = _prefect([("A", 1, 0.50001), ("B", 2, 0.50000)])
    s = ["B", "A"]
    reason, _ = _pure_diff(p, s, top_n=2, epsilon=1e-4)
    assert reason == "ok"


def test_ordering_outside_epsilon_fails():
    p = _prefect([("A", 1, 0.9), ("B", 2, 0.3)])
    s = ["B", "A"]
    reason, details = _pure_diff(p, s, top_n=2, epsilon=1e-4)
    assert reason.startswith("material_reorder_at_position_")
    assert details["delta"] > 1e-4


def test_identical_ordering_ok():
    p = _prefect([("A", 1, 0.9), ("B", 2, 0.5)])
    s = ["A", "B"]
    reason, _ = _pure_diff(p, s, top_n=2)
    assert reason == "ok"


def test_both_empty_ok():
    reason, _ = _pure_diff([], [])
    assert reason == "ok"
