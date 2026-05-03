#!/usr/bin/env bash
# Phase 11Z — safe dev-DB backup with retention.
#
# Creates a timestamped pg_dump under .backups/. Refuses to overwrite
# an existing file. Prints row counts before/after. Trims old files
# (keeps newest N, never deletes the newest).
#
# DOES NOT run `docker compose down -v`. DOES NOT touch
# `compose_pgdata`. Read-only operation against the running container.
#
# Usage:
#   scripts/backup_dev_db.sh                 # schema + data
#   scripts/backup_dev_db.sh --data-only
#   scripts/backup_dev_db.sh --schema-only
#   BACKUP_KEEP=5 scripts/backup_dev_db.sh   # keep newest 5 (default 10)
#   BACKUP_DIR=/somewhere scripts/backup_dev_db.sh
#
# Exit codes:
#   0  ok
#   2  refused (file exists, bad arg, container not reachable)

set -euo pipefail

CONTAINER="${BACKUP_PG_CONTAINER:-compose-db-1}"
DB_USER="${POSTGRES_USER:-invest}"
DB_NAME="${POSTGRES_DB:-investment_platform}"
BACKUP_DIR="${BACKUP_DIR:-.backups}"
KEEP="${BACKUP_KEEP:-10}"

mode="full"
extra=()
for a in "$@"; do
  case "$a" in
    --data-only)   mode="data";   extra+=("--data-only" "--inserts") ;;
    --schema-only) mode="schema"; extra+=("--schema-only") ;;
    -h|--help)
      grep -E '^# ' "$0" | sed -E 's/^# ?//' | head -25
      exit 0
      ;;
    *)
      echo "[backup] unknown arg: $a" >&2
      exit 2
      ;;
  esac
done

if ! docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" \
       >/dev/null 2>&1; then
  echo "[backup] cannot reach $CONTAINER / $DB_NAME" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d_%H%M%S)"
out="${BACKUP_DIR}/devdb_${mode}_${ts}.sql"

if [[ -e "$out" ]]; then
  echo "[backup] REFUSED: file already exists: $out" >&2
  exit 2
fi

echo "[backup] container=$CONTAINER db=$DB_NAME mode=$mode out=$out"
echo "[backup] row counts BEFORE:"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -c "
  SELECT 'paper_trade='        || count(*) FROM paper_trade
  UNION ALL SELECT 'paper_position='    || count(*) FROM paper_position
  UNION ALL SELECT 'paper_trade_log='   || count(*) FROM paper_trade_log
  UNION ALL SELECT 'paper_run_log='     || count(*) FROM paper_run_log
  UNION ALL SELECT 'paper_shadow_log='  || count(*) FROM paper_shadow_log
  UNION ALL SELECT 'decision_log='      || count(*) FROM decision_log
  UNION ALL SELECT 'recommendation='    || count(*) FROM recommendation
  UNION ALL SELECT 'account='           || count(*) FROM account
  UNION ALL SELECT 'asset='             || count(*) FROM asset
  UNION ALL SELECT 'price_bar='         || count(*) FROM price_bar
  UNION ALL SELECT 'context_daily='     || count(*) FROM context_daily
  UNION ALL SELECT 'candidate_idea='    || count(*) FROM candidate_idea;
" | sed 's/^/  /'

# Stream pg_dump straight to file. `--no-owner` makes restores
# portable across users.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --no-owner "${extra[@]}" > "$out"

bytes=$(wc -c < "$out" | tr -d ' ')
echo "[backup] wrote $out ($bytes bytes)"
echo "[backup] row counts AFTER (sanity — no writes happened):"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -c "
  SELECT 'paper_trade=' || count(*) FROM paper_trade;
" | sed 's/^/  /'

# Retention — keep newest N files matching devdb_*.sql, never delete
# the most recent.
if [[ "$KEEP" -gt 0 ]]; then
  mapfile -t files < <(
    ls -1t "$BACKUP_DIR"/devdb_*.sql 2>/dev/null || true
  )
  if (( ${#files[@]} > KEEP )); then
    # Skip the first KEEP entries (newest), delete the rest.
    for f in "${files[@]:KEEP}"; do
      # Defensive: never delete the file we just wrote.
      if [[ "$f" == "$out" ]]; then continue; fi
      echo "[backup] retention: removing old $f"
      rm -- "$f"
    done
  fi
fi

echo "[backup] OK"
