# Mock Options Chain Fixtures (Phase 11P.4)

These JSON fixtures feed `scripts/run_options_paper_eval.py
--mock-chain-from <path>` for offline data generation. Each fixture
seeds `options_chain_snapshot` rows tagged `provider=mock_local`,
`provider_version=11O.1-mock`. NEVER conflate with real provider data.

## Fixtures

| File | Underlying | Regime | DTE |
|---|---|---|---|
| `spy_calm_30d.json`     | SPY | calm, qualifies put credit spread + iron condor | 30 |
| `spy_stress_30d.json`   | SPY | high IV, qualifies iron condor only             | 30 |
| `qqq_calm_30d.json`     | QQQ | calm, qualifies put credit spread + iron condor | 30 |
| `iwm_volatile_45d.json` | IWM | elevated vol, qualifies iron condor             | 45 |
| `gld_low_iv_30d.json`   | GLD | low IV, qualifies put credit spread             | 30 |
| `tlt_event_45d.json`    | TLT | macro-event window, qualifies iron condor       | 45 |

## Author guide

Each fixture must:

1. Match the `_validate_mock_payload` schema in
   `scripts/run_options_paper_eval.py`:
   * top-level `snapshot_at_utc` (ISO datetime, UTC)
   * `rows: list[object]`
   * each row has the required fields:
     `underlying, expiry, strike, option_type, option_symbol,
     bid, ask`
2. Use `option_type` of `PUT` or `CALL` (or `P` / `C`).
3. Use ISO-format `expiry` date.
4. Pass the v1 liquidity filter:
   * `bid > 0`
   * `ask > bid`
   * `ask - bid <= 0.10`
   * `open_interest >= 500`
   * `quote_age_seconds <= 60`
5. Place at least one short candidate with `|delta|` in `[0.20, 0.35]`
   to satisfy the rule's delta band.
6. Provide a long protective leg at the correct side of the short
   strike (lower for puts, higher for calls).
7. Use `expiry - snapshot_at_utc.date()` in `[21, 45]` days.

## Run

```
python -m scripts.run_options_paper_eval \
    --date <snapshot date> \
    --underlyings <SYMBOL> \
    --mock-chain-from data/test/mock_chains/<file> \
    --dry-run
```

Then re-run with `--commit --confirm-commit YES --allow-mock-commit`
once dry-run output looks correct.

## Tagging

Mock-seeded rows always carry:
* `options_chain_snapshot.provider = 'mock_local'`
* `options_chain_snapshot.provider_version = '11O.1-mock'`

Audit JSONL log under `logs/options_paper_eval_<date>.jsonl` records
the trade in the same shape as real-provider runs.
