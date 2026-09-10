#!/usr/bin/env sh
# Restore a backup made by backup.sh. This REPLACES the current database and files.
# Usage: infrastructure/scripts/restore.sh backups/20260101T000000Z
set -eu
DIR="${1:?usage: restore.sh <backup-dir>}"
COMPOSE="docker compose -f infrastructure/compose.prod.yaml --env-file .env"
(cd "$DIR" && sha256sum -c SHA256SUMS)

printf 'This replaces the database and uploaded files with %s. Type "restore" to continue: ' "$DIR"
read -r answer
[ "$answer" = "restore" ] || { echo "Aborted."; exit 1; }

$COMPOSE stop web worker scheduler
$COMPOSE exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
$COMPOSE exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$DIR/database.dump"
$COMPOSE run --rm -T --no-deps web sh -c 'rm -rf /data/media/* && tar -C /data -xzf -' < "$DIR/media.tar.gz"
$COMPOSE up -d web worker scheduler
echo "Restored from $DIR"
