#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/opt/fishing-firm-preprod
ENV_FILE="$APP_DIR/.env"
COMPOSE_FILE="$APP_DIR/compose.yml"
SMOKE_SCRIPT="$APP_DIR/release-smoke-check.py"
STATE_DIR=/var/lib/fishing-firm-preprod
PREVIOUS_TAG_FILE="$STATE_DIR/previous-tag"
LOCK_FILE=/run/lock/fishing-firm-preprod-release.lock

if [[ $EUID -ne 0 ]]; then
  echo "This command must be run through sudo." >&2
  exit 1
fi

operation=${1:-}
requested_tag=${2:-}
if [[ "$operation" != deploy && "$operation" != rollback ]]; then
  echo "Usage: fishing-preprod-release deploy <40-character-commit-sha>" >&2
  echo "       fishing-preprod-release rollback [40-character-commit-sha]" >&2
  exit 2
fi

install -d -o root -g root -m 0700 "$STATE_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another pre-production deployment is already running." >&2
  exit 1
fi

for command_name in docker python3 flock; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done
[[ -f "$ENV_FILE" && -f "$COMPOSE_FILE" && -f "$SMOKE_SCRIPT" ]] || {
  echo "Pre-production files are missing. Run deploy/preprod/host-setup.sh first." >&2
  exit 1
}

read_env() {
  local key=$1
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

set_env_value() {
  local file=$1 key=$2 value=$3 temporary
  temporary=$(mktemp "${file}.tmp.XXXXXX")
  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 { print key "=" value; replaced = 1; next }
    { print }
    END { if (!replaced) print key "=" value }
  ' "$file" > "$temporary"
  chmod 0600 "$temporary"
  chown root:root "$temporary"
  mv "$temporary" "$file"
}

validate_tag() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || {
    echo "Image tag must be a full 40-character lowercase commit SHA." >&2
    return 1
  }
}

compose() {
  local env_file=$1
  shift
  docker compose --project-name fishing-firm-preprod \
    --env-file "$env_file" -f "$COMPOSE_FILE" "$@"
}

wait_for_health() {
  local api_id db_id api_health db_health attempt
  for attempt in $(seq 1 60); do
    api_id=$(compose "$ENV_FILE" ps -q api 2>/dev/null || true)
    db_id=$(compose "$ENV_FILE" ps -q db 2>/dev/null || true)
    api_health=""
    db_health=""
    if [[ -n "$api_id" ]]; then
      api_health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$api_id" 2>/dev/null || true)
    fi
    if [[ -n "$db_id" ]]; then
      db_health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$db_id" 2>/dev/null || true)
    fi
    if [[ "$api_health" == healthy && "$db_health" == healthy ]]; then
      return 0
    fi
    if [[ "$api_health" == unhealthy || "$db_health" == unhealthy || "$api_health" == exited || "$db_health" == exited ]]; then
      break
    fi
    sleep 2
  done
  echo "Container healthcheck failed (api=${api_health:-missing}, db=${db_health:-missing})." >&2
  compose "$ENV_FILE" ps >&2 || true
  return 1
}

smoke_check() {
  local tag=$1 port
  port=$(read_env APP_PORT)
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && (( port >= 1 && port <= 65535 )) || {
    echo "APP_PORT must be a valid TCP port in .env." >&2
    return 1
  }
  python3 "$SMOKE_SCRIPT" --url "http://127.0.0.1:${port}" \
    --expected-version "$tag" --expected-commit "$tag"
}

run_checks() {
  local tag=$1
  wait_for_health && smoke_check "$tag"
}

current_tag=$(read_env IMAGE_TAG)
image_repository=$(read_env IMAGE_REPOSITORY)
admin_password=$(read_env POSTGRES_PASSWORD)
app_password=$(read_env POSTGRES_APP_PASSWORD)
[[ -n "$admin_password" && "$admin_password" != CHANGE_ME* ]] || {
  echo "POSTGRES_PASSWORD is missing or still contains the example placeholder." >&2
  exit 1
}
[[ -n "$app_password" && "$app_password" != CHANGE_ME* ]] || {
  echo "POSTGRES_APP_PASSWORD is missing or still contains the example placeholder." >&2
  exit 1
}
[[ "$admin_password" != "$app_password" ]] || {
  echo "Use different passwords for the database administrator and application role." >&2
  exit 1
}
[[ "$image_repository" =~ ^docker\.io/[a-z0-9][a-z0-9._-]*/fishing-firm$ ]] || {
  echo "IMAGE_REPOSITORY must be docker.io/<dockerhub-user>/fishing-firm in .env." >&2
  exit 1
}

if [[ "$operation" == rollback && -z "$requested_tag" ]]; then
  [[ -s "$PREVIOUS_TAG_FILE" ]] || {
    echo "No previous successful release is recorded." >&2
    exit 1
  }
  requested_tag=$(cat "$PREVIOUS_TAG_FILE")
fi
validate_tag "$requested_tag"

candidate_env=$(mktemp "$APP_DIR/.env.candidate.XXXXXX")
trap 'rm -f "$candidate_env"' EXIT
cp "$ENV_FILE" "$candidate_env"
chmod 0600 "$candidate_env"
set_env_value "$candidate_env" IMAGE_TAG "$requested_tag"
set_env_value "$candidate_env" APP_VERSION "$requested_tag"
set_env_value "$candidate_env" APP_COMMIT "$requested_tag"

# Validate all required configuration before pulling or replacing a running container.
compose "$candidate_env" config --quiet

image_ref="${image_repository}:${requested_tag}"
if [[ "$operation" == rollback ]] && docker image inspect "$image_ref" >/dev/null 2>&1; then
  echo "Using cached previous image: $image_ref"
else
  echo "Pulling release image from registry: $image_ref"
  docker pull "$image_ref"
fi

# Start the isolated pre-production database if this is the first release.
compose "$candidate_env" up -d db
# Wait until the database is healthy before replacing the API.
db_id=$(compose "$candidate_env" ps -q db)
for attempt in $(seq 1 60); do
  db_health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$db_id" 2>/dev/null || true)
  [[ "$db_health" == healthy ]] && break
  [[ "$db_health" == unhealthy || "$db_health" == exited ]] && break
  sleep 2
done
if [[ "$db_health" != healthy ]]; then
  echo "Pre-production database is not healthy; current API release was not changed." >&2
  exit 1
fi

previous_env=$(mktemp "$STATE_DIR/previous-env.XXXXXX")
cp "$ENV_FILE" "$previous_env"
chmod 0600 "$previous_env"
chown root:root "$previous_env"
cp "$candidate_env" "$ENV_FILE"
chmod 0600 "$ENV_FILE"

if compose "$ENV_FILE" up -d --no-deps --force-recreate --no-build --pull never api \
    && run_checks "$requested_tag"; then
  if [[ "$current_tag" =~ ^[0-9a-f]{40}$ && "$current_tag" != "$requested_tag" ]]; then
    printf '%s\n' "$current_tag" > "$PREVIOUS_TAG_FILE"
  fi
  rm -f "$previous_env"
  echo "[PASS] Pre-production release is healthy: $image_ref"
  exit 0
fi

echo "[FAIL] New release did not pass post-deployment checks." >&2
if [[ "$current_tag" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Restoring previous release: $current_tag" >&2
  cp "$previous_env" "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
  if compose "$ENV_FILE" up -d --no-deps --force-recreate --no-build --pull never api \
      && run_checks "$current_tag"; then
    echo "[PASS] Previous release restored, but this deployment remains failed." >&2
  else
    echo "[CRITICAL] Automatic rollback could not be verified. Inspect the pre-production host." >&2
  fi
else
  echo "No previous release exists; the first deployment could not be rolled back." >&2
fi
rm -f "$previous_env"
exit 1
