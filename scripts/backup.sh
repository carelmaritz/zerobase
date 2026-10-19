#!/usr/bin/env bash
# Dump the Zerobase database to ./backups/zerobase-YYYYmmdd-HHMMSS.sql.gz
# Run from the project directory on the Docker host:  ./scripts/backup.sh
#
# Restore with:
#   gunzip -c backups/<file>.sql.gz | docker compose exec -T db psql -U zerobase zerobase
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/zerobase-$(date +%Y%m%d-%H%M%S).sql.gz"

docker compose exec -T db pg_dump -U zerobase --clean --if-exists zerobase | gzip > "$out"
echo "Wrote $out"
