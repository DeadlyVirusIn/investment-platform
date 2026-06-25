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
# Machine-readable status JSON for the owner /api/admin/system dashboard.
# Written inside a DIRECTORY that the api bind-mounts read-only — mounting the
# dir (not the single file) avoids inode-pinning: the atomic tmp+mv rewrite
# creates a new inode each run, which a single-file mount would never see.
HEALTH_JSON="${ARTHOS_HEALTH_JSON:-$HOME/arthos-health/status.json}"
mkdir -p "$(dirname "$HEALTH_JSON")" 2>/dev/null
chmod 755 "$(dirname "$HEALTH_JSON")" 2>/dev/null
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
if curl -s --connect-timeout 10 https://app.arthosfinance.xyz/api/health 2>/dev/null | grep -q '"status":"ok"'; then
  API_HEALTH=ok
else
  API_HEALTH=bad; warns+=("api_health_bad")
fi

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
BOT=$(systemctl is-active ptcgpb-bot 2>/dev/null); [ "$BOT" = active ] || warns+=("ptcgpb-bot=$BOT")
TUNNEL=$(systemctl is-active cloudflared-arthos 2>/dev/null); [ "$TUNNEL" = active ] || warns+=("cloudflared-arthos=$TUNNEL")
WCRON=$([ "$(docker inspect -f '{{.State.Running}}' compose-worker-cron-1 2>/dev/null)" = "true" ] && echo running || echo down)
[ "$WCRON" = running ] || warns+=("worker-cron=$WCRON")
WTICK=$([ "$(docker inspect -f '{{.State.Running}}' compose-worker-tickloop-1 2>/dev/null)" = "true" ] && echo running || echo down)
[ "$WTICK" = running ] || warns+=("worker-tickloop=$WTICK")

STAMP="site=$SITE disk=${DISK}% mem_avail=${MEM_AVAIL}M swap_free=${SWAP_FREE}M job_age=${JOB_AGE:-?}h"
if [ ${#warns[@]} -eq 0 ]; then
  echo "$(ts) OK   $STAMP" >> "$LOG"
else
  echo "$(ts) WARN ${warns[*]} | $STAMP" >> "$LOG"
fi

# Machine-readable status JSON for the owner /api/admin/system dashboard.
# Atomic write (tmp + mv). Status fields only — never secrets. world-readable
# so the bind-mounted api container (different uid) can read it.
cat > "$HEALTH_JSON.tmp" <<JSON
{"ts":"$(ts)","site":"$SITE","api_health":"${API_HEALTH:-unknown}","tunnel":"${TUNNEL:-unknown}","bot":"${BOT:-unknown}","worker_cron":"${WCRON:-unknown}","worker_tickloop":"${WTICK:-unknown}","disk_pct":${DISK:-null},"mem_avail_mb":${MEM_AVAIL:-null},"swap_free_mb":${SWAP_FREE:-null},"job_age_h":${JOB_AGE:-null}}
JSON
chmod 644 "$HEALTH_JSON.tmp" 2>/dev/null
mv "$HEALTH_JSON.tmp" "$HEALTH_JSON" 2>/dev/null

# self-cap the log (never let it grow the disk)
tail -n "$LOG_MAX_LINES" "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"

# exit non-zero if any warning (useful for manual runs / future alerting)
[ ${#warns[@]} -eq 0 ]
