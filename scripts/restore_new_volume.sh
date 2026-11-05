#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:-backups/fishing.dump}"
RESTORE_PROJECT="${RESTORE_PROJECT:-fishing-restore}"
RESTORE_VOLUME="${RESTORE_PROJECT}_restore_data"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup not found: $BACKUP_FILE" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is required." >&2
  exit 2
fi
if docker volume inspect "$RESTORE_VOLUME" >/dev/null 2>&1; then
  echo "Refusing to overwrite existing restore volume '$RESTORE_VOLUME'." >&2
  echo "Inspect it first or choose another RESTORE_PROJECT, e.g. make restore-new-volume RESTORE_PROJECT=fishing-restore-2." >&2
  exit 2
fi

compose=(docker compose -p "$RESTORE_PROJECT" -f docker-compose.restore.yml)
count_sql="SELECT 'boats=' || (SELECT count(*) FROM boats) || ';crews=' || (SELECT count(*) FROM crews) || ';fish_types=' || (SELECT count(*) FROM fish_types) || ';trips=' || (SELECT count(*) FROM trips) || ';catches=' || (SELECT count(*) FROM catches);"
source_counts="$(printf '%s\n' "$count_sql" | docker compose exec -T db sh -c 'psql -Atq -U "$POSTGRES_USER" -d "$POSTGRES_DB"')"
echo "Source table row counts: $source_counts"
echo "Starting isolated restore database in a new volume: $RESTORE_VOLUME"
"${compose[@]}" up -d db

container_id="$("${compose[@]}" ps -q db)"
if [[ -z "$container_id" ]]; then
  echo "Restore database container was not created." >&2
  exit 1
fi
healthy=false
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    healthy=true
    break
  fi
  if [[ "$status" == "unhealthy" || "$status" == "exited" ]]; then
    break
  fi
  sleep 2
done
if [[ "$healthy" != true ]]; then
  echo "Restore database did not become healthy. Container is kept for investigation: $container_id" >&2
  exit 1
fi

# This is a custom-format pg_dump archive, streamed without copying it into the container.
"${compose[@]}" exec -T db sh -c 'pg_restore --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$BACKUP_FILE"
"${compose[@]}" exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /container-grants.sql'
restored_counts="$(printf '%s\n' "$count_sql" | "${compose[@]}" exec -T db sh -c 'psql -Atq -U "$POSTGRES_USER" -d "$POSTGRES_DB"')"
printf 'Source counts:   %s\nRestored counts: %s\n' "$source_counts" "$restored_counts"
if [[ "$restored_counts" != "$source_counts" ]]; then
  echo "Restore verification failed: row counts differ across one or more core tables. The new volume is kept for investigation." >&2
  exit 1
fi

echo "Restore completed in new volume '$RESTORE_VOLUME'. The restore container is left running for defense inspection."
echo "Do not use 'docker compose down -v' for the main project; it deletes the main database volume."
