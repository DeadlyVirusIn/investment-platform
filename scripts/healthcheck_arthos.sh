#!/usr/bin/env bash
# ArthOS lightweight healthcheck — intended to run every 15 min via cron.
#
# Writes ONE line per run to $LOG (OK or WARN ...). The log self-caps to
# LOG_MAX_LINES on every run so it can never grow the disk (the VM sits ~83%).
# Read-only: checks only. Never restarts anything (bot included).
#
# Checks: public site 200 · /api/health ok · worker job freshness ·
# disk% · mem/swap headroom · bot active · cloudflared-arthos active ·
# worker-cron + worker-tickloop running.
set -u

REPO="${ARTHOS_REPO:-$HOME/investment-platform}"
LOG="${ARTHOS_HEALTH_LOG:-$HOME/arthos-health.log}"
LOG_MAX_LINES=500          # 15-min cadence → ~5 days history, ~50 KB cap
DISK_WARN=90               # percent
MEM_AVAIL_WARN_MB=400
SWAP_FREE_WARN_MB=512
JOB_FRESH_HOURS=26

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
warns=()

# 1. public WebUI
SITE=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 https://app.arthosfinance.xyz/ 2>/dev/null)
[ "$SITE" = "200" ] || warns+=("site=$SITE")

# 2. /api/health
curl -s --connect-timeout 10 https://app.arthosfinance.xyz/api/health 2>/dev/null | grep -q '"status":"ok"' \
  || warns+=("api_health_bad")

# 3. worker job freshness — latest job_run age (hours)
P="docker compose --env-file $REPO/.env -f $REPO/infra/compose/docker-compose.yml -f $REPO/infra/compose/docker-compose.prod.yml"
JOB_AGE=$(cd "$REPO" 2>/dev/null && $P exec -T db psql -U invest_prod -d investment_platform -tAc \
  "SELECT round(EXTRACT(EPOCH FROM (now() - max(started_at)))/3600, 1) FROM job_run" 2>/dev/null | tr -d '[:space:]')
if [ -z "$JOB_AGE" ]; then
  warns+=("job_age=unknown")
elif awk "BEGIN{exit !($JOB_AGE > $JOB_FRESH_HOURS)}"; then
  warns+=("job_stale=${JOB_AGE}h")
fi

# 4. disk
DISK=$(df / | awk 'NR==2{gsub("%","",$5); print $5}')
{ [ -n "$DISK" ] && [ "$DISK" -ge "$DISK_WARN" ]; } 2>/dev/null && warns+=("disk=${DISK}%")

# 5. memory + swap headroom (MB)
MEM_AVAIL=$(free -m | awk '/^Mem:/{print $7}')
SWAP_FREE=$(free -m | awk '/^Swap:/{print $4}')
{ [ -n "$MEM_AVAIL" ] && [ "$MEM_AVAIL" -lt "$MEM_AVAIL_WARN_MB" ]; } 2>/dev/null && warns+=("mem_avail=${MEM_AVAIL}M")
{ [ -n "$SWAP_FREE" ] && [ "$SWAP_FREE" -lt "$SWAP_FREE_WARN_MB" ]; } 2>/dev/null && warns+=("swap_free=${SWAP_FREE}M")

# 6-8. services active (read-only; bot is checked, never touched)
for svc in ptcgpb-bot cloudflared-arthos; do
  systemctl is-active --quiet "$svc" || warns+=("$svc=down")
done
for c in compose-worker-cron-1 compose-worker-tickloop-1; do
  [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ] || warns+=("$c=down")
done

STAMP="site=$SITE disk=${DISK}% mem_avail=${MEM_AVAIL}M swap_free=${SWAP_FREE}M job_age=${JOB_AGE:-?}h"
if [ ${#warns[@]} -eq 0 ]; then
  echo "$(ts) OK   $STAMP" >> "$LOG"
else
  echo "$(ts) WARN ${warns[*]} | $STAMP" >> "$LOG"
fi

# self-cap the log (never let it grow the disk)
tail -n "$LOG_MAX_LINES" "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"

# exit non-zero if any warning (useful for manual runs / future alerting)
[ ${#warns[@]} -eq 0 ]
