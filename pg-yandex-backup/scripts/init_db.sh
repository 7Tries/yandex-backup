#!/usr/bin/env bash
# init_db.sh — applies SQL init scripts to PostgreSQL.
# Used both in Docker (via docker-entrypoint-initdb.d) and manually.
set -euo pipefail

HOST="${POSTGRES_HOST:-}"
PORT="${POSTGRES_PORT:-5432}"
DB="${POSTGRES_DB:-postgres}"
ADMIN_USER="${POSTGRES_ADMIN_USER:-postgres}"
ADMIN_PASSWORD="${POSTGRES_ADMIN_PASSWORD:-}"
BACKUP_PASSWORD="${POSTGRES_BACKUP_PASSWORD:-${POSTGRES_PASSWORD_BACKUP:-backup_secret}}"

export PGPASSWORD="$ADMIN_PASSWORD"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="${SQL_DIR:-/sql}"
if [ ! -d "$SQL_DIR" ]; then
  SQL_DIR="$(cd "$SCRIPT_DIR/../sql" 2>/dev/null && pwd || echo "/sql")"
fi

PSQL_OPTS=()
if [ -n "$HOST" ]; then
  PSQL_OPTS=(-h "$HOST" -p "$PORT")
fi

echo "[init_db] Waiting for PostgreSQL..."
until psql "${PSQL_OPTS[@]}" -U "$ADMIN_USER" -d "$DB" -c 'SELECT 1' &>/dev/null; do
  sleep 1
done
echo "[init_db] PostgreSQL is ready."

echo "[init_db] Applying 01_notify_triggers.sql from ${SQL_DIR}..."
psql "${PSQL_OPTS[@]}" -U "$ADMIN_USER" -d "$DB" \
  -f "${SQL_DIR}/01_notify_triggers.sql"

echo "[init_db] Applying 02_backup_role.sql from ${SQL_DIR}..."
psql "${PSQL_OPTS[@]}" -U "$ADMIN_USER" -d "$DB" \
  -v "backup_password=${BACKUP_PASSWORD}" \
  -v "dbname=${DB}" \
  -f "${SQL_DIR}/02_backup_role.sql"

echo "[init_db] Done."
