#!/usr/bin/env bash
# Daily observation snapshot — 6 metrics, read-only.
# Run from host:    bash scripts/daily_observation.sh
# Run inside cron:  /app/scripts/daily_observation.sh
#
# Prints a single timestamped block; designed for `docker logs`,
# cron mail, or piping into a paste buffer.

set -u

readonly DB_C="${DB_CONTAINER:-compose-db-1}"
readonly DB_U="${DB_USER:-invest}"
readonly DB_N="${DB_NAME:-investment_platform}"
readonly API_BASE="${API_BASE:-http://127.0.0.1:8000}"

q() {
    docker exec "${DB_C}" psql -U "${DB_U}" -d "${DB_N}" -tAc "$1" 2>/dev/null
}

ts() { date -u '+%Y-%m-%d %H:%M:%S UTC'; }
hr() { printf '%s\n' '────────────────────────────────────────────────────────────'; }

hr
printf '[%s] DAILY OBSERVATION\n' "$(ts)"
hr

# 1. ingest_prices_daily success — join job_schedule + latest job_run
INGEST=$(q "SELECT COALESCE(jr.status, 'never') || ' @ ' ||
                   COALESCE(jr.started_at::date::text, 'never') ||
                   ' (next ' ||
                   COALESCE(js.next_run_at::date::text, '?') || ')'
            FROM job_schedule js
            LEFT JOIN LATERAL (
              SELECT status, started_at FROM job_run
              WHERE job_schedule_id = js.id
              ORDER BY started_at DESC LIMIT 1
            ) jr ON true
            WHERE js.name='ingest_prices_daily'")
printf '  ingest_prices_daily   : %s\n' "${INGEST:-?}"

# 2. paper_daily success — read latest paper_run_log row
PAPER=$(q "SELECT status || ' @ ' || run_date || ' (opened=' ||
                  COALESCE(trades_opened,0) || ' closed=' ||
                  COALESCE(trades_closed,0) || ')'
           FROM paper_run_log
           ORDER BY started_at DESC LIMIT 1")
printf '  paper_daily           : %s\n' "${PAPER:-?}"

# 3. latest_bar_date — features_daily preferred, fallback price_bar
LATEST_BAR=$(q "SELECT COALESCE(
                  (SELECT MAX(as_of_date)::text FROM features_daily),
                  (SELECT MAX(as_of_date)::text FROM context_daily),
                  (SELECT MAX(ts::date)::text FROM price_bar))")
printf '  latest_bar_date       : %s\n' "${LATEST_BAR:-?}"

# 4. paper_trade_log count
PT_COUNTS=$(q "SELECT 'total=' || COUNT(*) || ' open=' ||
                      COUNT(*) FILTER (WHERE status='open') ||
                      ' closed=' || COUNT(*) FILTER (WHERE status='closed')
               FROM paper_trade_log")
printf '  paper_trade_log       : %s\n' "${PT_COUNTS:-?}"

# 5. ml_model_run.labeled_row_count (latest)
ML_LABELS=$(q "SELECT 'labeled=' || labeled_row_count || ' rows=' ||
                      row_count || ' status=' || status ||
                      ' @ ' || created_at::date
               FROM ml_model_run
               ORDER BY created_at DESC LIMIT 1")
printf '  ml_model_run latest   : %s\n' "${ML_LABELS:-(no runs)}"

# 6. promotion_guard state — via API (preferred) or DB snapshot
PROMO=$(curl -s "${API_BASE}/api/ml/hybrid/promotion-status" 2>/dev/null \
        | grep -oE '"state":"[^"]+"' | head -1 | cut -d'"' -f4)
HD=$(curl -s "${API_BASE}/api/ml/hybrid/promotion-status" 2>/dev/null \
     | grep -oE '"healthy_day_count":[0-9]+' | cut -d: -f2)
printf '  promotion_guard       : %s (healthy_days=%s)\n' \
       "${PROMO:-?}" "${HD:-?}"

# Bonus context — ML mode + execution lock
MODE=$(curl -s "${API_BASE}/api/ml/hybrid/status" 2>/dev/null \
       | grep -oE '"mode":"[^"]+"' | head -1 | cut -d'"' -f4)
EXEC=$(curl -s "${API_BASE}/api/ml/hybrid/status" 2>/dev/null \
       | grep -oE '"ml_can_affect_trades":(true|false)' | cut -d: -f2)
printf '  ml_hybrid_mode        : %s\n' "${MODE:-?}"
printf '  ml_can_affect_trades  : %s\n' "${EXEC:-?}"

hr
