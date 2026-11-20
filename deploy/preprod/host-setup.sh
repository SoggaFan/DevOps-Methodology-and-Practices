#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_USER=fishing-deploy
APP_DIR=/opt/fishing-firm-preprod
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PUBLIC_KEY=${1:-}

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./deploy/preprod/host-setup.sh 'ssh-ed25519 AAAA... comment'" >&2
  exit 1
fi
if [[ -z "$PUBLIC_KEY" || "$PUBLIC_KEY" != ssh-* || "$PUBLIC_KEY" == *$'\n'* ]]; then
  echo "Pass the public SSH key for the dedicated fishing-deploy account." >&2
  exit 2
fi

for command_name in docker visudo python3 flock; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done
docker compose version >/dev/null

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --user-group --shell /bin/bash "$DEPLOY_USER"
fi
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0700 "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
if ! grep -Fqx -- "$PUBLIC_KEY" "/home/$DEPLOY_USER/.ssh/authorized_keys"; then
  printf '%s\n' "$PUBLIC_KEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 0600 "/home/$DEPLOY_USER/.ssh/authorized_keys"

install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/sql" /var/lib/fishing-firm-preprod
install -m 0644 "$SCRIPT_DIR/compose.yml" "$APP_DIR/compose.yml"
install -m 0644 "$PROJECT_DIR/sql/000_create_app_user.sql" "$APP_DIR/sql/000_create_app_user.sql"
install -m 0644 "$PROJECT_DIR/sql/001_schema.sql" "$APP_DIR/sql/001_schema.sql"
install -m 0644 "$PROJECT_DIR/sql/002_seed.sql" "$APP_DIR/sql/002_seed.sql"
install -m 0644 "$PROJECT_DIR/sql/003_grants.sql" "$APP_DIR/sql/003_grants.sql"
install -m 0750 "$SCRIPT_DIR/remote-release.sh" /usr/local/sbin/fishing-preprod-release
install -m 0644 "$SCRIPT_DIR/release-smoke-check.py" "$APP_DIR/release-smoke-check.py"

if [[ ! -f "$APP_DIR/.env" ]]; then
  install -m 0600 "$SCRIPT_DIR/.env.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env. Edit passwords and IMAGE_REPOSITORY before first deployment."
fi
chown root:root "$APP_DIR/.env"
chmod 0600 "$APP_DIR/.env"

printf '%s\n' "$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/fishing-preprod-release" \
  > /etc/sudoers.d/fishing-preprod-release
chmod 0440 /etc/sudoers.d/fishing-preprod-release
visudo -cf /etc/sudoers.d/fishing-preprod-release

# Do not add fishing-deploy to the docker group. It can invoke only the fixed release wrapper via sudo.
echo "Pre-production host files installed."
echo "Next: edit $APP_DIR/.env, authenticate root's Docker client to Docker Hub, then configure GitHub Actions variables/secrets."
