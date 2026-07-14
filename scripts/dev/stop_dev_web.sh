#!/usr/bin/env bash
# Project-scoped dev-web shutdown (post-incident hygiene, 2026-07-09).
#
# WHY THIS EXISTS: a broad `taskkill //F //IM node.exe //FI "WINDOWTITLE eq *"`
# was once used to stop the vite dev server — the WINDOWTITLE filter matches
# everything, so that command kills EVERY node process on the machine
# (editors, MCP servers, unrelated tools). Never do that again.
#
# Correct pattern: start_dev_web.sh records the dev server's PID; this
# script kills exactly that process tree and nothing else.

set -euo pipefail
PIDFILE="${TMPDIR:-/tmp}/arthos-dev-web.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "no pidfile at $PIDFILE — nothing to stop (or it wasn't started via start_dev_web.sh)"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if ! kill -0 "$PID" 2>/dev/null; then
  echo "pid $PID not running — removing stale pidfile"
  rm -f "$PIDFILE"
  exit 0
fi

# Kill the process tree (Windows Git Bash: use taskkill scoped to the PID).
if command -v taskkill >/dev/null 2>&1; then
  taskkill //PID "$PID" //T //F >/dev/null
else
  kill -TERM -- "-$PID" 2>/dev/null || kill "$PID"
fi
rm -f "$PIDFILE"
echo "stopped dev web server (pid $PID) — only that process tree"
