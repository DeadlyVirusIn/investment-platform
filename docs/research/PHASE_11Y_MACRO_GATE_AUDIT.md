# Phase 11Y — Macro Gate Audit (audit-only, no code change)

**Window:** 2026-04-27 → 2026-05-01
**Author:** automated audit, 2026-05-01
**Scope:** read-only diagnostic of the 4 production macro gates
(`rates_calm`, `vrp_supportive`, `credit_stable`, `liquidity_expanding`)
to determine whether each `FALSE` outcome reflects genuine economic
signal or is forced by missing/stale/coerced inputs.
**Strict rule honored:** no behavior changes proposed for execution
in this phase. No code edits made.

---

## 1. Executive Summary

The 0/4 favorable outcome on **2026-04-29, 04-30, 05-01** is **almost
entirely a backfill-coverage artifact, not an economic signal.**

- 4-27 / 4-28 (computed by the wide 5-year backfill on 4-29 00:49 UTC):
  **2/4 favorable** (`vrp_supportive=T`, `credit_stable=T`).
- 4-29 / 4-30 / 5-01 (computed by three **single-day** backfills on
  5-01 13:42–13:44 UTC): **0/4 favorable** for all three days.

The single-day backfills fetched FRED with `start=end=<that day>`,
which returned ≤1 observation per series — far below the minimum
history required by every gate compute function (`rates_calm` needs
6 DGS10 obs, `credit_stable` needs 21 HYOAS, `vrp_supportive` needs
22 SPY + 30 VRP rolling, `liquidity_expanding` needs WALCL/WTREGEN/RRP
at as_of *and* as_of−20d). All four functions returned `None`.

`scripts/backfill_macro_features.py:312` then collapsed every `None`
into `value_bool=False` and inserted it as `status='production'`
into `context_daily`. There is **currently no signal in the schema
that distinguishes "macro unfavorable" from "data unavailable."**

If the 4-29..5-01 days had been covered by a wide-window backfill,
the economically-correct picture is approximately:

| Date | rates_calm | vrp_supportive | credit_stable | liquidity_expanding | n_pass |
|------|------------|----------------|---------------|---------------------|--------|
| 4-27 | F (real)   | T (real)       | T (real)      | F (real)            | 2/4    |
| 4-28 | F (real)   | T (real)       | T (real)      | F (real)            | 2/4    |
| 4-29 | F (real)   | T (likely)     | T (real)      | F (real)            | ~2/4   |
| 4-30 | F (real)   | ? (data lag)   | T (real)      | F (real)            | ~1–2/4 |
| 5-01 | F (real)   | ? (data lag)   | T (real)      | F (real)            | ~1–2/4 |

The economically-real signal across the window is "stress-leaning,
2/4 favorable" — which under production logic is still `directional`
(needs ≥2). The ratification of `0/4` and consequent flat
production output is almost certainly **not** a macro change.

---

## 2. Where the Gates Are Computed

| Gate | File | Function | Min history |
|------|------|----------|-------------|
| rates_calm          | `apps/api/src/data/features/rates.py:21`     | `compute_rates_calm`         | 6 DGS10 obs (5-day Δ) |
| vrp_supportive      | `apps/api/src/data/features/vol.py:27`       | `compute_vrp_supportive`     | 22 SPY + 1 VIX + 30 VRP rolling (6M) |
| credit_stable       | `apps/api/src/data/features/credit.py:12`    | `compute_credit_stable`      | 21 HYOAS obs (or 21 HYG) |
| liquidity_expanding | `apps/api/src/data/features/liquidity.py:24` | `compute_liquidity_expanding`| WALCL+WTREGEN+RRP at as_of AND as_of−20d |

Dispatch: `scripts/backfill_macro_features.py:243-249` →
`compute_gates_for_day`. Persist (the systemic finding):
`scripts/backfill_macro_features.py:312`:

```python
value_bool = bool(val) if val is not None else False
```

This is the **single point where missing-data is silently
indistinguishable from an unfavorable macro reading**. All four
functions explicitly return `None` when inputs are too short; this
line collapses every `None` to `False` and writes
`status='production'`. There is no `'unknown'` / `'insufficient_data'`
status enum value in `context_daily.ck_status` (only
`production|candidate|diagnostic`).

---

## 3. FRED Input Coverage (raw `features_daily`)

```
DGS10        : 1250 obs, 2021-04-28 → 2026-04-29   (no 4-28, no 4-30, no 5-01)
VIXCLS       : 1286 obs, 2021-04-28 → 2026-04-30   (no 4-28, no 5-01)
BAMLH0A0HYM2 :  787 obs, 2023-04-30 → 2026-04-30   (no 4-28, no 5-01)
WALCL        :  262 obs, 2021-04-28 → 2026-04-29   (weekly Wed; no 4-30, no 5-01)
WTREGEN      :  262 obs, 2021-04-28 → 2026-04-29   (weekly Wed; no 4-30, no 5-01)
RRPONTSYD    : 1250 obs, 2021-04-28 → 2026-04-30   (only 4-28 and 4-30 present in window)
SPY (price)  : 1089 obs, 2022-01-03 → 2026-04-30
```

**Why dates are missing:**

- **4-28 missing for DGS10/VIX/HYOAS:** wide backfill ran at
  2026-04-29 00:49 UTC, before FRED published 4-28 values
  (publication lag T+1 around mid-day US). Subsequent single-day
  reruns for 4-29/4-30/5-1 never re-requested 4-28, so it was
  permanently missed.
- **WALCL/WTREGEN are weekly (Wed):** 4-29 (Wed) is the most
  recent value; 4-30, 5-01 only ever existed via forward-fill in
  compute, which works correctly via `s.loc[:as_of].iloc[-1]`.
- **5-01 returns 0 rows for every series:** FRED hasn't published
  any 5-01 values yet at audit time (run was 5-01 13:44 UTC, before
  publication for most daily series).

---

## 4. Per-Day × Per-Gate Diagnostic

Legend for **category**:
`REAL` = computed correctly with sufficient history;
`ARTIFACT-coerced` = `None` returned by compute fn → coerced to
`FALSE` at persist line 312;
`STALE-OK` = used latest-available input (forward-fill via
`s.loc[:as_of]`); result is real even though latest input is older.

### 4-27 (Mon) — wide backfill 4-29 00:49 UTC

| Gate | Result | Inputs at compute | Threshold | Reason | Category |
|------|--------|-------------------|-----------|--------|----------|
| rates_calm          | **F** | DGS10(4-27)=4.35, DGS10(4-20)=4.26 | d10y_5d < 0 | +0.09 (rates rising) | REAL |
| vrp_supportive      | **T** | full 6M VRP series | VRP > 6M median | passes | REAL |
| credit_stable       | **T** | full HYOAS history (785 obs) | HYOAS Δ20d ≤ 0 | spreads compressed | REAL |
| liquidity_expanding | **F** | WALCL/WTREGEN/RRP full | NetLiq Δ20d > 0 | TGA up, balance sheet flat | REAL |

### 4-28 (Tue) — wide backfill 4-29 00:49 UTC

| Gate | Result | Inputs | Reason | Category |
|------|--------|--------|--------|----------|
| rates_calm          | **F** | latest DGS10 ≤ 4-28 = 4-27(4.35), 5d back = 4-20(4.26) | +0.09 | REAL (STALE-OK; 4-28 not yet published, latest ≤ as_of correctly used) |
| vrp_supportive      | **T** | full | passes | REAL |
| credit_stable       | **T** | full HYOAS | compressed | REAL |
| liquidity_expanding | **F** | weekly WALCL still 4-22 | ΔNetLiq < 0 | REAL |

### 4-29 (Wed) — single-day backfill 5-01 13:42 UTC

`fetched_counts={DGS10:1, VIX:1, HYOAS:1, WALCL:1, WTREGEN:1, RRP:1}`

| Gate | Result | Series len | Required | compute returned | Persist line 312 |
|------|--------|------------|----------|------------------|------------------|
| rates_calm          | **F** | 1 DGS10 | ≥6 | `None` | `None → False` |
| vrp_supportive      | **F** | 1 SPY day inside fetch window | ≥22 | `None` | `None → False` |
| credit_stable       | **F** | 1 HYOAS | ≥21 | `None` | `None → False` |
| liquidity_expanding | **F** | as_of OK; as_of−20d none in fetch | both required | `None` | `None → False` |

**All 4 = ARTIFACT-coerced.**
Audit log line: `"samples": [{"as_of_date":"2026-04-29", "rates_calm":null, "vrp_supportive":null, "credit_stable":null, "liquidity_expanding":null, "n_pass":0}]`

What it would have been with full history:
- rates_calm: DGS10(4-29)=4.42 − DGS10(4-22)=4.30 = +0.12 → **FALSE (real)**
- credit_stable: HYOAS(4-29)=2.82, HYOAS(21-back)=3.28 → −0.46 ≤ 0 → **TRUE (real)**
- liquidity_expanding: NetLiq(4-29)=5,718,020 vs NetLiq(4-9)=5,945,494 → ΔNetLiq=−227,474 → **FALSE (real)**
- vrp_supportive: cannot recompute from this audit alone; on 4-27/4-28 it was T, very likely T on 4-29.

### 4-30 (Thu) — single-day backfill 5-01 13:43 UTC

`fetched_counts={DGS10:0, VIX:1, HYOAS:1, WALCL:0, WTREGEN:0, RRP:1}`

DGS10/WALCL/WTREGEN: **publication lag** — FRED had not released
4-30 values when the fetch ran. Note: WALCL/WTREGEN are weekly
(Wed), so 4-30 (Thu) was never going to exist as a fresh data point
— the gate function correctly forward-fills via `s.loc[:as_of]`,
but the single-day fetch produced no rows at all, defeating that.

All 4 → `None` → `False`. **All 4 = ARTIFACT-coerced.**

### 5-01 (Fri) — single-day backfill 5-01 13:44 UTC

`fetched_counts={DGS10:0, VIX:0, HYOAS:0, WALCL:0, WTREGEN:0, RRP:0}`

**Zero data fetched.** All 4 → `None` → `False`. **All 4 = ARTIFACT-coerced.**

---

## 5. Same-day vs T+1 Availability Analysis

Daily FRED rates / vol / credit series (DGS10, VIXCLS,
BAMLH0A0HYM2) publish with ~T+1 lag; values for trading day D
typically appear mid-day D+1.

This means **every day's macro gate value is correctly only
computable starting D+1 — the wide backfill that ran at 4-29 00:49
UTC was *too early* to capture 4-28's DGS10/VIX/HYOAS values.**

The compute functions handle T+1 correctly via `s.loc[:as_of]`
forward-fill (uses latest-available row ≤ as_of). But this only
works **when sufficient history is in the in-memory series** —
which the per-day backfill destroyed.

---

## 6. Per-Gate Conclusions

| Gate | True economic signal in window | DB value 4-29..5-01 | Verdict |
|------|--------------------------------|---------------------|---------|
| **rates_calm**          | FALSE consistently (rates rising) | FALSE | DB happens to be correct, but for the wrong reason (coerced from `None`, not computed). Coincidental match. |
| **vrp_supportive**      | TRUE on 4-27/28, likely TRUE on 4-29 | FALSE | **Likely incorrect.** Coerced from `None`. |
| **credit_stable**       | TRUE (HY OAS compressing) | FALSE | **Incorrect.** Real value would be TRUE. Coerced from `None`. |
| **liquidity_expanding** | FALSE (NetLiq contracting) | FALSE | DB happens to be correct, but for the wrong reason (coerced from `None`). Coincidental match. |

**Summary: 2/4 of the FALSE values on 4-29..5-01 are coincidentally
correct (the real value is also FALSE) and 2/4 are wrong (real
value is TRUE, coerced to FALSE). Net result: production sees
0/4 favorable when reality is ~2/4 favorable.**

That is the difference between `stress` (≤1 favorable → engine off)
and `directional` (≥2 favorable → engine eligible). The artifact
flipped the platform from `directional` to `stress` for three days
on no economic basis.

---

## 7. Recommended Future Fixes (DO NOT IMPLEMENT THIS PHASE)

These are recorded for operator review only.

1. **Distinguish "data unavailable" from "macro unfavorable" in
   `context_daily`.** Add a fourth status (e.g., `'unknown'` or
   `'insufficient_data'`) to `ck_status` and a nullable
   `value_bool`. Update `persist_context` line 312 to write
   `status='unknown'`/`value_bool=NULL` when the compute fn returns
   `None`. Downstream selector should treat `unknown` as
   non-favorable for safety, but should record it distinctly in
   `paper_run_log` so operators can see the difference.

2. **T+1 lag-aware evaluation.** When computing for date D, the
   backfill should fetch a wide window ending at D, not
   `start=end=D`. This is already how the 5-year backfill works;
   the per-day reruns should use the same call (`--start=D-365 --end=D`
   minimum, or just always call with `--start=<5y-ago> --end=D`
   and rely on `ON CONFLICT DO NOTHING` to skip existing rows).

3. **Forward-fill for slow series.** WALCL/WTREGEN are weekly
   (Wed). The compute fns already forward-fill via
   `s.loc[:as_of].iloc[-1]`. The remediation needs to ensure the
   *fetch* covers a wide enough window so that forward-fill has
   data to use.

4. **Backfill scheduling.** No code change in this phase, but the
   prior incident (Phase 11W) plus this one suggests macro
   backfill should be triggered by the daily loop, not manual
   per-day reruns. The wide 5-year-window form is idempotent and
   safe to run nightly.

5. **Audit-log alarm.** When a backfill run reports any
   `gate_aggregates.{name}.total > 0` and `pct == 0.0` for **all
   four gates simultaneously across only 1 business day**, that's
   a signature of the artifact described here. Worth adding to the
   diagnostics layer as a soft alert.

---

## 8. Validation Block

**SQL run (read-only):**
- `SELECT … FROM context_daily WHERE as_of_date BETWEEN '2026-04-27' AND '2026-05-01' AND context_name IN (4 gates)` — 20 rows, all `status='production'`.
- `SELECT feature_name, COUNT(*) … FROM features_daily WHERE feature_name IN (6 FRED series) GROUP BY` — confirmed 1250/1286/787/262/262/1250 obs per series.
- `SELECT … FROM features_daily WHERE feature_name IN (…) AND as_of_date BETWEEN '2026-04-01' AND '2026-05-01'` — 92 rows, confirmed 4-28 / 4-30 / 5-01 gaps per series.
- `SELECT … FROM features_daily WHERE feature_name='BAMLH0A0HYM2' ORDER BY as_of_date DESC LIMIT 25` — confirmed HYOAS history reaches 2026-03-26 in last 25 obs.
- `SELECT a.symbol, COUNT(p.*) … FROM price_bar p JOIN asset a ON …` — SPY: 1089 bars, 2022-01-03 → 2026-04-30.

**Files inspected (read-only, no edits):**
- `apps/api/src/data/features/rates.py` (26 lines)
- `apps/api/src/data/features/vol.py` (54 lines)
- `apps/api/src/data/features/credit.py` (27 lines)
- `apps/api/src/data/features/liquidity.py` (34 lines)
- `scripts/backfill_macro_features.py` (1–360+ lines, dispatch at 243-249, persist at 312)
- `apps/api/src/api/safe_gate_evolution.py` / shadow module (Phase 11X context)

**Audit JSONL logs reviewed:**
- `logs/macro_backfill_2021-04-28_2026-04-28.jsonl` — wide; fetched 1249/1284/785/261/261/1248 rows; computed 4-27 (2/4) and 4-28 (2/4) correctly.
- `logs/macro_backfill_2026-04-29_2026-04-29.jsonl` — single-day; fetched 1/1/1/1/1/1; **all 4 gates returned `null`**; persisted as 4 FALSE rows.
- `logs/macro_backfill_2026-04-30_2026-04-30.jsonl` — single-day; fetched 0/1/1/0/0/1; all 4 `null`; 4 FALSE rows.
- `logs/macro_backfill_2026-05-01_2026-05-01.jsonl` — single-day; fetched 0/0/0/0/0/0; all 4 `null`; 4 FALSE rows.

**Code-change confirmation:** none made. No file under
`apps/api/src/data/features/`, no
`scripts/backfill_macro_features.py`, no `infra/alembic/versions/*`,
and no production gate logic was modified during this audit.
`git status` will show this audit doc as the only addition.

---

## 9. Bottom Line

The 0/4 macro reading on 2026-04-29 / 04-30 / 05-01 is **a
data-coverage artifact**, produced by three single-day backfills
that fetched ≤1 observation per series — far below every gate's
minimum history requirement — and then silently coerced the
resulting `None` outputs to `FALSE` via
`backfill_macro_features.py:312`. The economically-correct
reading for the window is approximately **2/4 favorable, same as
4-27 and 4-28**, which would have kept the platform in
`directional` mode rather than flipping it to `stress`.

The single most impactful audit finding is line 312:
`value_bool = bool(val) if val is not None else False`. Every
recommended future fix flows from giving that line a third state.
