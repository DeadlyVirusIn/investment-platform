#!/usr/bin/env bash
# Start the vite dev server with a pidfile so stop_dev_web.sh can shut down
# exactly this process tree (see stop_dev_web.sh for the incident note).
# Optional dev-preview flags: pass e.g. DEV_FLAGS="VITE_DEV_TRUST_CENTER=1".

set -euo pipefail
cd "$(dirname "$0")/../../apps/web"
PIDFILE="${TMPDIR:-/tmp}/arthos-dev-web.pid"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "dev web already running (pid $(cat "$PIDFILE")) — stop_dev_web.sh first"
  exit 1
fi

env ${DEV_FLAGS:-} npx vite --port "${DEV_WEB_PORT:-5199}" --strictPort &
echo $! > "$PIDFILE"
echo "dev web started (pid $(cat "$PIDFILE"), port ${DEV_WEB_PORT:-5199}); stop with scripts/dev/stop_dev_web.sh"
wait
