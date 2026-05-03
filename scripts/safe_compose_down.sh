#!/usr/bin/env bash
# scripts/safe_compose_down.sh — Phase 11Z incident-response wrapper.
#
# Refuses to run `docker compose down -v` (volume-destroying) against
# the dev DB volume `compose_pgdata` unless the operator passes
# BOTH a hard env confirmation AND an explicit --force-dev-wipe
# flag. Prints current row counts before refusing so the operator
# sees what they would lose.
#
# Usage:
#   scripts/safe_compose_down.sh                # plain `down`, no -v
#   scripts/safe_compose_down.sh -v             # rejected
#   REQUIRE_VOLUME_DELETE_CONFIRMATION=I_UNDERSTAND_THIS_DELETES_DATABASE \
#     scripts/safe_compose_down.sh -v --force-dev-wipe
#
# Exit codes:
#   0  ok
#   2  refused due to missing confirmation
#   3  unrecognized flag combination
#   4  cannot reach Postgres for pre-wipe count

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-infra/compose/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"
PROTECTED_VOLUME="${PROTECTED_VOLUME:-compose_pgdata}"

want_volume_wipe="false"
want_force_dev_wipe="false"
extra_args=()
for a in "$@"; do
  case "$a" in
    -v|--volumes) want_volume_wipe="true" ;;
    --force-dev-wipe) want_force_dev_wipe="true" ;;
    *) extra_args+=("$a") ;;
  esac
done

if [[ "$want_volume_wipe" == "false" ]]; then
  # Plain `down` is allowed (no volume destruction).
  exec docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
    down "${extra_args[@]}"
fi

# From here on we are about to delete a volume. Hard-stop unless
# operator explicitly confirms.

confirm="${REQUIRE_VOLUME_DELETE_CONFIRMATION:-}"
expected="I_UNDERSTAND_THIS_DELETES_DATABASE"
if [[ "$confirm" != "$expected" ]]; then
  echo "[safe_compose_down] REFUSED: -v specified but confirmation env" >&2
  echo "[safe_compose_down] missing or wrong." >&2
  echo "[safe_compose_down] Set:" >&2
  echo "  REQUIRE_VOLUME_DELETE_CONFIRMATION=$expected" >&2
  exit 2
fi

if [[ "$want_force_dev_wipe" != "true" ]]; then
  echo "[safe_compose_down] REFUSED: dev volume '$PROTECTED_VOLUME'" >&2
  echo "[safe_compose_down] requires --force-dev-wipe." >&2
  exit 2
fi

# Print current row counts so operator sees what they're losing.
echo "[safe_compose_down] About to wipe volume: $PROTECTED_VOLUME"
echo "[safe_compose_down] Current dev DB state:"
if ! docker exec compose-db-1 psql -U invest -d investment_platform -c "
  SELECT
    (SELECT count(*) FROM asset)            AS asset,
    (SELECT count(*) FROM price_bar)        AS price_bar,
    (SELECT count(*) FROM paper_trade)      AS paper_trade,
    (SELECT count(*) FROM paper_run_log)    AS paper_run_log,
    (SELECT count(*) FROM decision_log)     AS decision_log,
    (SELECT count(*) FROM paper_shadow_log) AS paper_shadow_log,
    (SELECT count(*) FROM paper_trade_log)  AS paper_trade_log,
    (SELECT count(*) FROM candidate_idea)   AS candidate_idea,
    (SELECT count(*) FROM context_daily)    AS context_daily;
" 2>/dev/null; then
  echo "[safe_compose_down] WARNING: cannot reach Postgres; aborting" >&2
  exit 4
fi
echo
echo "[safe_compose_down] You have 5 seconds to Ctrl-C. Proceeding…"
sleep 5

exec docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  down -v "${extra_args[@]}"
