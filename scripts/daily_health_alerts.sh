#!/usr/bin/env bash
# Daily health alerts — read-only checks, prints WARN/ALERT lines.
# Exit code: 0 = all clean, 1 = at least one warning, 2 = at least one alert.
#
# Designed to chain into mail / Slack / log without coupling to the
# in-app trading alerts system. No backend mutation.
#
# Run from host:    bash scripts/daily_health_alerts.sh
# Run inside cron:  /app/scripts/daily_health_alerts.sh

set -u

readonly DB_C="${DB_CONTAINER:-compose-db-1}"
readonly DB_U="${DB_USER:-invest}"
readonly DB_N="${DB_NAME:-investment_platform}"
readonly API_BASE="${API_BASE:-http://127.0.0.1:8000}"

# T+5 from oldest unlabeled paper trade — once exceeded, missing labels
# warrant an ALERT not just an info.
readonly LABEL_DEADLINE_DAYS="${LABEL_DEADLINE_DAYS:-7}"

q() {
    docker exec "${DB_C}" psql -U "${DB_U}" -d "${DB_N}" -tAc "$1" 2>/dev/null
}

ts() { date -u '+%Y-%m-%d %H:%M:%S UTC'; }

WARN_COUNT=0
ALERT_COUNT=0

emit() {
    # $1 = level (INFO|WARN|ALERT), $2 = id, $3 = msg
    printf '[%s] %-5s %-32s %s\n' "$(ts)" "$1" "$2" "$3"
    case "$1" in
        WARN)  WARN_COUNT=$((WARN_COUNT + 1)) ;;
        ALERT) ALERT_COUNT=$((ALERT_COUNT + 1)) ;;
    esac
}

# ───────────────────────────────────────────────────────────────────────
# 1. ingest_prices_daily — failed?
# ───────────────────────────────────────────────────────────────────────
INGEST_STATUS=$(q "
    SELECT jr.status FROM job_schedule js
    LEFT JOIN LATERAL (
      SELECT status FROM job_run
      WHERE job_schedule_id = js.id
      ORDER BY started_at DESC LIMIT 1
    ) jr ON true
    WHERE js.name='ingest_prices_daily'")
case "${INGEST_STATUS:-}" in
    success)  emit INFO  ingest_prices_daily "OK" ;;
    error)    emit ALERT ingest_prices_daily "last run errored" ;;
    "")       emit WARN  ingest_prices_daily "no run history" ;;
    *)        emit WARN  ingest_prices_daily "status=${INGEST_STATUS}" ;;
esac

# ───────────────────────────────────────────────────────────────────────
# 2. daily loop — failed last run?
# ───────────────────────────────────────────────────────────────────────
LOOP_FAIL=$(q "
    SELECT CASE WHEN
      (SELECT 1) IS NOT NULL THEN 'check'
    END")
# Use marker file via API
DL_STATE=$(curl -s "${API_BASE}/api/scheduler/health" 2>/dev/null \
           | tr ',{}' '\n' | grep -E '"last_(success|failure)_at":' \
           | head -2)
DL_OK=$(printf '%s' "$DL_STATE" | grep -E '"last_success_at":"[^"]+"' | head -1)
DL_FAIL=$(printf '%s' "$DL_STATE" | grep -E '"last_failure_at":"[^"]+"' | head -1)
if [[ -n "$DL_FAIL" && -z "$DL_OK" ]]; then
    emit ALERT daily_loop "last run FAILED, no success on record"
elif [[ -n "$DL_FAIL" && -n "$DL_OK" ]]; then
    # Compare timestamps via string sort (ISO8601 UTC)
    SUCC_TS=$(printf '%s' "$DL_OK"  | sed 's/.*"\([^"]\+\)"/\1/')
    FAIL_TS=$(printf '%s' "$DL_FAIL" | sed 's/.*"\([^"]\+\)"/\1/')
    if [[ "$FAIL_TS" > "$SUCC_TS" ]]; then
        emit ALERT daily_loop "last failure newer than last success"
    else
        emit INFO  daily_loop "OK"
    fi
else
    emit INFO  daily_loop "OK"
fi

# ───────────────────────────────────────────────────────────────────────
# 3. paper_daily — unexpectedly skipped?
#    (latest paper_run_log status='partial' AND no trades opened/closed)
# ───────────────────────────────────────────────────────────────────────
PD_STATE=$(q "SELECT status || '|' ||
                     COALESCE(trades_opened,0) || '|' ||
                     COALESCE(trades_closed,0) || '|' ||
                     run_date::text
              FROM paper_run_log
              ORDER BY started_at DESC LIMIT 1")
IFS='|' read -r PD_STATUS PD_OPEN PD_CLOSE PD_DATE <<<"${PD_STATE}"
if [[ "${PD_STATUS:-}" == "failed" ]]; then
    emit ALERT paper_daily "FAILED on ${PD_DATE}"
elif [[ "${PD_STATUS:-}" == "partial" \
        && "${PD_OPEN:-0}" == "0" \
        && "${PD_CLOSE:-0}" == "0" ]]; then
    # PARTIAL with 0 trades is normal during accumulation;
    # only WARN when latest_bar is fresh enough that paper_daily
    # SHOULD have produced a decision.
    LB=$(q "SELECT MAX(as_of_date)::text FROM context_daily")
    if [[ "${LB:-}" > "${PD_DATE:-1970-01-01}" ]]; then
        emit WARN paper_daily \
             "skipped on ${PD_DATE} but bars exist through ${LB}"
    else
        emit INFO paper_daily "no-trade day on ${PD_DATE} (expected)"
    fi
else
    emit INFO paper_daily \
         "${PD_STATUS}: opened=${PD_OPEN} closed=${PD_CLOSE} (${PD_DATE})"
fi

# ───────────────────────────────────────────────────────────────────────
# 4. labeled_row_count still 0 past T+5?
# ───────────────────────────────────────────────────────────────────────
LABELED=$(q "SELECT COALESCE(labeled_row_count,0)
             FROM ml_model_run
             ORDER BY created_at DESC LIMIT 1")
OLDEST_OPEN=$(q "
    SELECT EXTRACT(DAY FROM (CURRENT_DATE - MIN(entry_date)))::int
    FROM paper_trade_log
    WHERE entry_date >= CURRENT_DATE - INTERVAL '60 days'")
if [[ -z "${LABELED}" ]]; then
    emit INFO labels "no ml_model_run yet"
elif [[ "${LABELED}" -gt 0 ]]; then
    emit INFO labels "${LABELED} labels available"
elif [[ -n "${OLDEST_OPEN}" \
        && "${OLDEST_OPEN}" -gt "${LABEL_DEADLINE_DAYS}" ]]; then
    emit ALERT labels \
         "0 labels after ${OLDEST_OPEN}d (deadline ${LABEL_DEADLINE_DAYS}d)"
else
    emit INFO labels "0 (still within accumulation window)"
fi

# ───────────────────────────────────────────────────────────────────────
# 5. ML_CAN_AFFECT_TRADES not false?
# ───────────────────────────────────────────────────────────────────────
EXEC_LOCK=$(curl -s "${API_BASE}/api/ml/hybrid/status" 2>/dev/null \
            | grep -oE '"ml_can_affect_trades":(true|false)' | cut -d: -f2)
if [[ "${EXEC_LOCK}" == "false" ]]; then
    emit INFO ml_can_affect_trades "false (locked)"
elif [[ "${EXEC_LOCK}" == "true" ]]; then
    emit ALERT ml_can_affect_trades "TRUE — execution unlocked!"
else
    emit WARN ml_can_affect_trades "could not read API status"
fi

# ───────────────────────────────────────────────────────────────────────
# 6. ML_HYBRID_MODE not advisory?
# ───────────────────────────────────────────────────────────────────────
HMODE=$(curl -s "${API_BASE}/api/ml/hybrid/status" 2>/dev/null \
        | grep -oE '"mode":"[^"]+"' | head -1 | cut -d'"' -f4)
if [[ "${HMODE}" == "advisory" ]]; then
    emit INFO ml_hybrid_mode "advisory"
elif [[ "${HMODE}" == "paper_reduce" ]]; then
    emit ALERT ml_hybrid_mode "paper_reduce — NOT advisory"
else
    emit WARN ml_hybrid_mode "unknown mode ${HMODE}"
fi

# ───────────────────────────────────────────────────────────────────────
printf -- '----\n'
printf 'summary: %d alert(s), %d warn(s)\n' "${ALERT_COUNT}" "${WARN_COUNT}"
if [[ ${ALERT_COUNT} -gt 0 ]]; then
    exit 2
elif [[ ${WARN_COUNT} -gt 0 ]]; then
    exit 1
fi
exit 0
