#!/usr/bin/env bash
# Production DB backup — streamed gzip, tight retention.
#
# Streams pg_dump straight through gzip to a timestamped file under
# .backups/ (no uncompressed intermediate — safe on a tight disk).
# Read-only against the running container. Never touches the data volume.
# Trims old files (keeps newest N).
#
# Usage:
#   scripts/backup_prod_db.sh                  # schema + data (gz)
#   BACKUP_KEEP=3 scripts/backup_prod_db.sh    # keep newest 3 (default 3)
#
# Env:
#   POSTGRES_USER (default invest_prod), POSTGRES_DB (default investment_platform)
#   BACKUP_PG_CONTAINER (default compose-db-1), BACKUP_DIR (default .backups)
#
# Exit codes: 0 ok · 2 refused (container unreachable / verify failed)
#
# NOTE: same-disk backups protect against bad migrations / accidental
# drops / corruption — NOT against disk failure. For DR, copy the newest
# .gz off-box (OCI Object Storage) — see docs/ops/DB_BACKUP_AND_REPLAY_POLICY.md.

set -euo pipefail

CONTAINER="${BACKUP_PG_CONTAINER:-compose-db-1}"
DB_USER="${POSTGRES_USER:-invest_prod}"
DB_NAME="${POSTGRES_DB:-investment_platform}"
BACKUP_DIR="${BACKUP_DIR:-.backups}"
KEEP="${BACKUP_KEEP:-3}"

if ! docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
  echo "[backup] cannot reach $CONTAINER / $DB_NAME" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d_%H%M%S)"
out="${BACKUP_DIR}/proddb_full_${ts}.sql.gz"

echo "[backup] container=$CONTAINER db=$DB_NAME out=$out"
# Stream dump -> gzip -> file. --no-owner for portable restore.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner \
  | gzip -c > "$out"

bytes=$(wc -c < "$out" | tr -d ' ')
echo "[backup] wrote $out ($bytes bytes)"

# Verify integrity: gzip stream is intact AND the dump trailer is present.
if ! gzip -t "$out" 2>/dev/null; then
  echo "[backup] VERIFY FAILED: corrupt gzip — removing $out" >&2
  rm -f "$out"; exit 2
fi
if ! gunzip -c "$out" | tail -5 | grep -q "PostgreSQL database dump complete"; then
  echo "[backup] VERIFY FAILED: dump trailer missing — removing $out" >&2
  rm -f "$out"; exit 2
fi
echo "[backup] verify OK (gzip intact + dump complete)"

# Retention — keep newest N, never delete the file just written.
if [[ "$KEEP" -gt 0 ]]; then
  mapfile -t files < <(ls -1t "$BACKUP_DIR"/proddb_full_*.sql.gz 2>/dev/null || true)
  if (( ${#files[@]} > KEEP )); then
    for f in "${files[@]:KEEP}"; do
      [[ "$f" == "$out" ]] && continue
      echo "[backup] retention: removing old $f"
      rm -- "$f"
    done
  fi
fi

echo "[backup] OK"
