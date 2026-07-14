> **ARCHIVED 2026-07-09** — describes the pre-auth single-user Phase-0 design
> (2026-04); superseded by the paper-trading book model in apps/api/src/domain/paper_trading/.
> Kept for history; do not use for implementation.

# Ledger Model

## Overview

The ledger is the source of truth for what you own and what it cost.
It follows a standard double-entry-inspired chain:

```
Transaction  →  Lot  →  PositionSnapshot  →  P&L
```

---

## Entities

### Transaction

The raw record of a buy, sell, dividend, split, or crypto purchase.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `symbol_id` | FK → symbol | |
| `txn_type` | enum | BUY, SELL, DIVIDEND, SPLIT, PURCHASE (MoonPay) |
| `quantity` | numeric | Positive for acquisitions, negative for disposals |
| `price` | numeric | Per-unit cost in `currency` |
| `currency` | varchar | USD, EUR, BTC, ETH, … |
| `fees` | numeric | Broker commission or network gas fee |
| `settled_at` | timestamptz | Trade settlement date |
| `source` | enum | MANUAL, CSV_IMPORT, BROKER_API, WALLET, MOONPAY |
| `external_id` | varchar | Broker order ID or blockchain tx hash |
| `raw_payload` | jsonb | Original import data (preserved for audit) |

### Lot

Created from BUY transactions via FIFO lot assignment.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `transaction_id` | FK → transaction | Source BUY |
| `symbol_id` | FK → symbol | |
| `quantity_original` | numeric | Units acquired |
| `quantity_remaining` | numeric | Units not yet sold |
| `cost_basis` | numeric | Total cost (price × qty + fees) |
| `acquired_at` | date | For short/long-term capital gain classification |
| `closed_at` | date | Null until fully consumed |

### PositionSnapshot

Materialised daily by the worker. Fast reads for the dashboard.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `symbol_id` | FK → symbol | |
| `snapshot_date` | date | |
| `quantity` | numeric | Sum of `lot.quantity_remaining` at this date |
| `avg_cost_basis` | numeric | Weighted average |
| `market_value` | numeric | `quantity × price_bar.close` |
| `unrealised_pnl` | numeric | `market_value − (quantity × avg_cost_basis)` |
| `unrealised_pnl_pct` | numeric | |

---

## P&L Calculation

### Unrealised P&L

```
unrealised_pnl = market_value − (quantity × avg_cost_basis)
```

Computed in the daily snapshot materialisation job.

### Realised P&L (FIFO)

On each SELL transaction:
1. Walk open lots oldest-first (FIFO).
2. Consume quantity from each lot, recording `cost_basis_consumed`.
3. `realised_pnl = proceeds − cost_basis_consumed − fees`.
4. Classify as short-term (held < 1 year) or long-term.

---

## Corporate Actions

### Stock Splits

A SPLIT transaction adjusts all open lots for the symbol:
```
lot.quantity_remaining *= split_ratio
lot.cost_basis /= split_ratio
```

### Cash Dividends

A DIVIDEND transaction is recorded as income; it does not affect lot cost
basis (in the US model — adjust for your jurisdiction).

---

## MoonPay Purchase Records

MoonPay webhooks arrive as `txn_type = PURCHASE`. The raw webhook payload is
stored in `transaction.raw_payload`. The fiat amount and crypto amount are
extracted and mapped to a BUY transaction for lot assignment.

Fields extracted from MoonPay webhook:
- `baseCurrencyAmount` → fiat cost
- `quoteCurrencyAmount` → crypto quantity
- `networkFeeAmount` → fees
- `cryptoTransactionId` → external_id (tx hash)

---

## Currency Handling

All P&L is normalised to USD using the `fx_rate` stored at transaction time.
The worker fetches daily FX rates from Tiingo or FRED and records them in
the `fx_rate` table.
