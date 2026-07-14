# recommendation_outcome Reconstruction Audit — Wave 3A.1 (2026-07-14)

## Verdict: **NO OUTCOME BACKFILL JUSTIFIED — the "gap" is not an outcome gap**

The Wave 3A fold gap was attributed to missing resolved outcomes in
2024-H2/2025. Investigation proves the outcomes are fine; the
**recommendations themselves don't exist** for those windows.

## Root-cause table (by generation month; dev DB, all actions)

| Period | Recs | Outcome rows | Resolved | Reason |
|---|---|---|---|---|
| 2024-02..05 | 3,969 | 3,969 | 3,969 (100%) | replay era `+replay:dev1-2024` — fully resolved |
| **2024-06..2025-01** | **0** | 0 | 0 | **no replay ever generated** — permanently absent unless a new replay is run |
| 2025-02..05 | 3,906 | 3,906 | 3,906 (100%) | replay era `+replay:dev1-2025` — fully resolved |
| **2025-06..2026-01** | **0** | 0 | 0 | **no replay ever generated** |
| 2026-02..04 | 12,458 | 12,458 | 12,458 (100%) | replay variants `dev1-nm/long/31d/31d-hc` |
| 2026-05 | 49,106 | 49,090 | 49,085 | live engine starts (`0.1.0`) + replay variants; 16 rows missing, 5 open |
| 2026-06 | 62,783 | 62,755 | 8,897 | live; mostly **legitimately censored** (30d windows still open; `score_outcomes` labels ≥30d-old recs nightly and is healthy) |
| 2026-07 | 33,040 | 33,040 | 0 | live; all inside the 30d window — legitimately open |

Reconstructable-outcome scope: **44 recommendations without outcome rows +
5 stale-open (>45d)** out of 163,262 — immaterial to any evidence claim
(0.03%), and the stale-open rows are inside `score_outcomes`' normal
queue. Under the mission's own rule ("do not claim improved evidence
merely because more rows are produced"), running a reconstruction
machine for 49 rows manufactures process, not evidence. **No inserts were
made; existing outcomes byte-untouched.**

If fold depth for 2024-H2/2025 is ever wanted, the honest instrument is a
NEW engine replay for those windows (generating new, clearly-versioned
recommendations) — a deliberate, separately-approved evidence campaign,
not an outcome backfill.

## The REAL Wave 3A evidence defect found: replay-variant pooling

2026 windows contain the SAME decisions replayed under up to **8
model_version strings** (`0.1.0`, `dev1-nm`, `dev1-20260616-long/-31d/
-31d-hc/-smoke`, yearly replays). Wave 3A's loader filtered only
action+window+universe ⇒ it **pooled duplicate correlated decisions**
(e.g. 2026-04: 4 variants × 100 identical Buys). Fixed in lab-1.1:

- spec gains `model_versions` scoping (part of the hashed identity);
- unscoped multi-version corpora now emit a **CRITICAL replay pooling
  warning** (blocks the no-critical-warnings gate);
- the dataset manifest records `distinct_model_versions` + the filter;
- pg test pins that scoping exactly halves a two-variant corpus.

Original Wave 3A runs are retained untouched; their pooling is disclosed
in the addendum to the validation report.

## Reconciliation & same-bar policy (assessed, not exercised)

Because zero rows were inserted, the stratified replay/reconciliation
machinery was not needed. For the record, the stored outcome policy
(`score_outcomes` + `triple_barrier_label`) resolves same-bar
target+stop crossings by bar ordering only — any future reconstruction
campaign MUST classify unknown intra-bar ordering as `ambiguous_same_bar`
(never a chosen winner), per the mission policy. This is recorded as the
binding policy (`outcome-rebuild-1`) for whenever a real backfill is
justified.
