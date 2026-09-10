#!/usr/bin/env sh
# Back up the database and uploaded files of the production compose stack.
# Usage: infrastructure/scripts/backup.sh [backup-dir]
set -eu
COMPOSE="docker compose -f infrastructure/compose.prod.yaml --env-file .env"
DIR="${1:-backups}/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DIR"

# Custom format: compressed, restorable table by table, consistent snapshot.
$COMPOSE exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$DIR/database.dump"
# Private attachments (photos, PDFs).
$COMPOSE exec -T web tar -C /data -czf - media > "$DIR/media.tar.gz"

sha256sum "$DIR"/* > "$DIR/SHA256SUMS"
echo "Backup written to $DIR"
