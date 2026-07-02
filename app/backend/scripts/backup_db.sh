#!/usr/bin/env bash
# Back up the Tradenet Postgres database to a compressed, restorable dump.
#
# The DB is the source of truth (238k+ marks + months of enrichment/backfills +
# users); `tm_pgdata` is a single Docker volume with no other copy, so a
# `docker compose down -v` or disk failure is unrecoverable without this.
#
# Runs `pg_dump -Fc` INSIDE the postgres container (no host psql client needed)
# and streams the custom-format dump to a host file, then prunes old dumps.
#
# Usage (from the repo root):
#   app/backend/scripts/backup_db.sh
#   BACKUP_DIR=/mnt/backups RETENTION=30 app/backend/scripts/backup_db.sh
#
# Schedule it (self-host example): a root crontab line
#   15 3 * * *  cd /path/to/Tradenet && BACKUP_DIR=/mnt/backups app/backend/scripts/backup_db.sh >> /var/log/tradenet-backup.log 2>&1
#
# Restore (DESTRUCTIVE — overwrites the target DB):
#   docker compose -f app/docker-compose.yml exec -T postgres \
#       pg_restore -U tm -d tm --clean --if-exists < BACKUP_DIR/<file>.dump
#
# Production (no compose): dump directly against the URL —
#   pg_dump "$TM_DATABASE_URL_SYNC" -Fc -f backup.dump
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION="${RETENTION:-14}"          # keep this many most-recent dumps
COMPOSE_FILE="${COMPOSE_FILE:-app/docker-compose.yml}"
PG_USER="${POSTGRES_USER:-tm}"
PG_DB="${POSTGRES_DB:-tm}"

mkdir -p "$BACKUP_DIR"
ts="$(date +%Y%m%d_%H%M%S)"
out="$BACKUP_DIR/tradenet_${PG_DB}_${ts}.dump"

# -T: no TTY so the dump streams cleanly to the host file.
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "$PG_USER" -d "$PG_DB" -Fc > "$out"

# A pg_dump that "succeeds" but produces an empty/tiny file is a failed backup;
# fail loudly so a scheduler alerts instead of silently rotating good dumps out.
if [ ! -s "$out" ] || [ "$(wc -c < "$out")" -lt 1024 ]; then
    echo "ERROR: backup file is empty/too small ($out) — aborting" >&2
    rm -f "$out"
    exit 1
fi

echo "OK: wrote $out ($(du -h "$out" | cut -f1))"

# Retention: delete everything older than the newest $RETENTION dumps.
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/tradenet_"${PG_DB}"_*.dump 2>/dev/null \
    | tail -n +"$((RETENTION + 1))" \
    | while read -r old; do echo "pruning $old"; rm -f "$old"; done
