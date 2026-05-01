#!/usr/bin/env bash
# Production daily job orchestrator.
#
# Runs required + optional jobs sequentially with:
#   • flock lock (prevents duplicate runs)
#   • timestamped START / SUCCESS / FAIL per job
#   • per-job exit code capture
#   • summary + health marker files
#   • non-zero exit if any REQUIRED job fails
#   • optional jobs skip gracefully on missing/error
#
# Invoked manually or from cron/supercronic.

set -u   # undefined vars are errors — but NOT set -e: we tolerate job failures

readonly LOCK_FILE="/tmp/quant_daily_loop.lock"
readonly HEALTH_OK="/tmp/last_daily_loop_success"
readonly HEALTH_FAIL="/tmp/last_daily_loop_failure"
readonly APP_DIR="${APP_DIR:-/app}"
readonly PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${APP_DIR}"
export PYTHONPATH="${APP_DIR}"

# ---------- logging ----------
ts() { date -u '+%Y-%m-%d %H:%M:%S UTC'; }
log() { printf '[%s] %s\n' "$(ts)" "$*"; }

# ---------- lock ----------
exec 9>"${LOCK_FILE}" || {
    log "ERROR cannot open lock file ${LOCK_FILE}"
    exit 1
}
if ! flock -n 9; then
    log "daily loop already running (lock ${LOCK_FILE}) — exiting cleanly"
    exit 0
fi
trap 'flock -u 9' EXIT

# ---------- counters ----------
TOTAL=0
SUCCESS=0
FAILED=0
SKIPPED=0
FAILED_REQUIRED=0
START_EPOCH=$(date +%s)

# run_job <name> <required|optional> <command...>
run_job() {
    local name="$1"; shift
    local kind="$1"; shift   # required|optional
    TOTAL=$((TOTAL + 1))

    log "START ${name}"
    # Optional existence check: if command's python module path not importable
    # treat as "not installed" when kind=optional.
    if [[ "${kind}" == "optional" ]]; then
        local modpath="${1:-}"
        # Heuristic: if invocation looks like "python -m foo.bar" and the
        # module doesn't exist → skip gracefully.
        if [[ "${modpath}" == "${PYTHON_BIN}" && "${2:-}" == "-m" ]]; then
            if ! ${PYTHON_BIN} -c "import importlib, sys; \
                sys.exit(0 if importlib.util.find_spec('${3}') else 1)" \
                2>/dev/null; then
                log "SKIP ${name} (module '${3}' not installed)"
                SKIPPED=$((SKIPPED + 1))
                return 0
            fi
        fi
    fi

    local job_start
    job_start=$(date +%s)
    # Run command; capture exit without killing loop.
    set +e
    "$@"
    local rc=$?
    set -e 2>/dev/null || true
    local job_end
    job_end=$(date +%s)
    local dur=$((job_end - job_start))

    if [[ ${rc} -eq 0 ]]; then
        log "SUCCESS ${name} (${dur}s)"
        SUCCESS=$((SUCCESS + 1))
    else
        log "FAIL ${name} exit=${rc} (${dur}s)"
        FAILED=$((FAILED + 1))
        if [[ "${kind}" == "required" ]]; then
            FAILED_REQUIRED=$((FAILED_REQUIRED + 1))
        fi
    fi
    return 0
}

# ---------- Job sequence ----------
log "==== daily loop start (pid $$) ===="

# 0. Engine pipeline (Phase 11W incident fix).
# Runs the macro → regime → factor → candidate stages BEFORE the
# market-data precheck so context_daily advances every trading day.
# Without this step the precheck pinned target_date to the last day
# of manually-backfilled macro data (2026-04-28 in the original
# incident), causing paper_run_log to upsert the same row indefinitely.
#
# As-of date defaults to today UTC; engine internally tolerates
# weekends + holidays.
ENGINE_AS_OF="$(date -u +%F)"
log "START engine_pipeline as_of=${ENGINE_AS_OF}"
set +e
${PYTHON_BIN} -m scripts.run_engine_pipeline --as-of "${ENGINE_AS_OF}"
engrc=$?
set -e 2>/dev/null || true
case "${engrc}" in
    0) log "SUCCESS engine_pipeline (macro+regime+factor+candidate ok)"
       SUCCESS=$((SUCCESS + 1))
       TOTAL=$((TOTAL + 1))  ;;
    3) log "SKIP engine_pipeline (no price_bar at or before ${ENGINE_AS_OF})"
       SKIPPED=$((SKIPPED + 1))
       TOTAL=$((TOTAL + 1))  ;;
    *) log "FAIL engine_pipeline rc=${engrc} (paper_daily will still run, " \
           "may stale)"
       FAILED=$((FAILED + 1))
       TOTAL=$((TOTAL + 1))  ;;
esac

# 1. Market-data readiness precheck.
# If the prior trading-day bar is missing, skip paper_daily cleanly
# (don't fail the loop) and still run downstream jobs that don't need
# fresh bars.
MARKET_DATA_READY=1
log "START market_data_readiness"
set +e
${PYTHON_BIN} -m scripts.check_market_data_ready
mdrc=$?
set -e 2>/dev/null || true
case "${mdrc}" in
    0) log "SUCCESS market_data_readiness (ready)"  ;;
    3) log "SKIP market_data_readiness (SKIPPED_MARKET_DATA_NOT_READY)"
       MARKET_DATA_READY=0
       SKIPPED=$((SKIPPED + 1))
       TOTAL=$((TOTAL + 1))  ;;
    *) log "FAIL market_data_readiness exit=${mdrc} (probe error, " \
           "treating as NOT ready)"
       MARKET_DATA_READY=0
       FAILED=$((FAILED + 1))
       TOTAL=$((TOTAL + 1))  ;;
esac

# 1. Paper trading run — required UNLESS market data not ready.
# Precheck writes /tmp/latest_bar_date when a valid bar exists; we pass
# that as --date so paper_daily processes the most recent completed
# trading day (Sat 03:30 → Fri bars, Tue 03:30 → Mon bars).
if [[ ${MARKET_DATA_READY} -eq 1 ]]; then
    TARGET_DATE=""
    if [[ -f /tmp/latest_bar_date ]]; then
        TARGET_DATE=$(cat /tmp/latest_bar_date 2>/dev/null | head -c 32)
    fi
    if [[ -n "${TARGET_DATE}" ]]; then
        log "paper_daily target_date=${TARGET_DATE} (from precheck)"
        run_job "paper_daily" "required" \
            "${PYTHON_BIN}" -m scripts.run_paper_daily \
            --force-recompute --date "${TARGET_DATE}"
    else
        log "paper_daily target_date=today (no precheck file; fallback)"
        run_job "paper_daily" "required" \
            "${PYTHON_BIN}" -m scripts.run_paper_daily --force-recompute
    fi
else
    log "SKIP paper_daily (market data not ready — safe skip)"
    SKIPPED=$((SKIPPED + 1))
    TOTAL=$((TOTAL + 1))
fi

# 2. Alpha nightly — required
run_job "alpha_nightly" "required" \
    "${PYTHON_BIN}" -m apps.api.src.jobs.alpha_nightly

# 3. ML shadow training/scoring — required
run_job "nightly_ml_shadow" "required" \
    "${PYTHON_BIN}" -m apps.api.src.jobs.nightly_ml_shadow

# 4. Hybrid monitor — required
run_job "ml_hybrid_monitor_nightly" "required" \
    "${PYTHON_BIN}" -m apps.api.src.jobs.ml_hybrid_monitor_nightly

# 5. Shadow strategy tracker — OPTIONAL (research only). Computes the
# tsmom_60_no_stress shadow signal + back-fills realized forward returns.
# NEVER writes to paper_trade_log; failure is non-blocking.
run_job "shadow_strategy_tsmom60_no_stress" "optional" \
    "${PYTHON_BIN}" -m scripts.run_shadow_strategy

# 5-6. Optional calibration refresh jobs were removed — audit 2026-04-24
# flagged that no `alpha_calibration_nightly` / `context_calibration_nightly`
# modules exist. Calibration is driven by alpha_nightly (which already ran
# at step 2) plus on-demand API endpoints:
#   POST /api/alpha/calibration/refresh
#   POST /api/alpha/context/refresh
# Re-add dedicated nightly jobs here once those modules land.

END_EPOCH=$(date +%s)
DURATION=$((END_EPOCH - START_EPOCH))

log "---- summary ----"
log "total=${TOTAL} success=${SUCCESS} failed=${FAILED} skipped=${SKIPPED} duration=${DURATION}s"

if [[ ${FAILED_REQUIRED} -gt 0 ]]; then
    log "daily loop result: REQUIRED JOB FAILED (${FAILED_REQUIRED})"
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "${HEALTH_FAIL}" 2>/dev/null || true
    exit 1
fi

log "daily loop result: OK"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "${HEALTH_OK}" 2>/dev/null || true
exit 0
