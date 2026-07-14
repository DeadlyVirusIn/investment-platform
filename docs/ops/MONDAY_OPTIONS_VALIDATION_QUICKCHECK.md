# Monday Options Validation — 5-Minute Quick Check

Run **Mon 2026-06-22 after ~15:00 UTC** (the pipeline ingests 14:15, generates
candidates 14:45 UTC; markets open — Fri Jun 19 was Juneteenth). Full context:
`docs/research/OPTIONS_TRADIER_PROD_VALIDATION.md`. Copy-paste, top to bottom.

## 1. Did stock chains ingest + candidates generate? (one query)

```bash
docker exec compose-db-1 psql -U invest -d investment_platform -c "
select 'snapshot' src, underlying, count(*) n
  from options_chain_snapshot
  where underlying in ('AAPL','MSFT','NVDA','AMZN','META','GOOGL')
    and snapshot_at_utc::date='2026-06-22'
  group by underlying
union all
select 'candidate', underlying, count(*)
  from options_strategy_candidate
  where underlying in ('AAPL','MSFT','NVDA','AMZN','META','GOOGL')
    and run_date='2026-06-22'
  group by underlying
order by 1,2;"
```

## 2. Do stocks reach the API? (one curl)

```bash
curl -s -H "X-Auth-User-Id: monday-check" \
  "http://localhost:5173/api/options/opportunities?limit=200" \
| python -c "import sys,json; o=json.load(sys.stdin); \
opps=o.get('opportunities',o if isinstance(o,list) else []); \
S={'AAPL','MSFT','NVDA','AMZN','META','GOOGL'}; \
hit=sorted({x['underlying'] for x in opps if x.get('underlying') in S}); \
print('stock underlyings in API:', hit, '->', 'PASS' if len(hit)>=3 else 'FAIL')"
```

## PASS / FAIL

- **PASS** = ≥3 of the 6 stocks have candidates (query 1) **and** appear in the
  API (query 2). → Tradier production solves it. **STOP. No Alpaca.** Update
  `OPTIONS_TRADIER_PROD_VALIDATION.md` with the result.
- **FAIL** = <3 stocks. → run step 3, then start the Alpaca plan.

## 3. ONLY IF FAIL — capture reject reasons per symbol (one command)

```bash
docker compose --env-file .env -f infra/compose/docker-compose.yml exec -T worker-tickloop \
  python -c "from apps.api.src.options.data.chain_ingest import ingest_universe; \
import json; print(json.dumps([{ 'u':getattr(s,'underlying',None), \
'inserted':getattr(s,'n_inserted',None), 'quotes':getattr(s,'n_provider_quotes',None), \
'rejects':getattr(s,'rejects',None)} for s in ingest_universe(universe=('AAPL','MSFT','NVDA'))], default=str))"
```
Record per symbol: `BID_NONPOSITIVE`, `WIDE_SPREAD`, `STALE_QUOTE`, OI gate,
and whether economics were missing. Those reject tallies are the evidence the
Alpaca plan needs (which gate fails, and by how much).

## 4. Optional UI confirm (skip if 1+2 already PASS)
`/v2/discover` → Options Practice tab → expect ≥1 individual-stock card with
Name (TICKER), "Ends on", and Practice entry/Best case/Max loss when priced.
