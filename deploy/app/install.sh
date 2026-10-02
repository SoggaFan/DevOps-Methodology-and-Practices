#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/fishing-firm
APP_USER=fishing
APP_GROUP=fishing
SERVICE_NAME=fishing-firm
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./deploy/app/install.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip curl

if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
  groupadd --system "$APP_GROUP"
fi
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --gid "$APP_GROUP" --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

install -d -o root -g "$APP_GROUP" -m 0750 "$APP_DIR"
rm -rf "$APP_DIR/app" "$APP_DIR/sql" "$APP_DIR/web"
cp -a "$PROJECT_DIR/app" "$PROJECT_DIR/sql" "$PROJECT_DIR/web" "$APP_DIR/"
install -m 0640 -o root -g "$APP_GROUP" "$PROJECT_DIR/requirements.txt" "$APP_DIR/requirements.txt"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R root:"$APP_GROUP" "$APP_DIR/app" "$APP_DIR/sql" "$APP_DIR/web" "$APP_DIR/requirements.txt"
find "$APP_DIR/app" "$APP_DIR/sql" "$APP_DIR/web" -type d -exec chmod 0750 {} +
find "$APP_DIR/app" "$APP_DIR/sql" "$APP_DIR/web" -type f -exec chmod 0640 {} +
chown -R "$APP_USER":"$APP_GROUP" "$APP_DIR/.venv"
find "$APP_DIR/.venv" -type d -exec chmod 0750 {} +
find "$APP_DIR/.venv/bin" -type f -exec chmod 0750 {} +

install -d -o root -g "$APP_GROUP" -m 0750 /etc/fishing-firm
if [[ ! -f /etc/fishing-firm/fishing-firm.env ]]; then
  install -o root -g "$APP_GROUP" -m 0640 "$PROJECT_DIR/deploy/app/fishing-firm.env.example" /etc/fishing-firm/fishing-firm.env
  echo "Edit /etc/fishing-firm/fishing-firm.env before starting the service."
fi

install -o root -g root -m 0644 "$PROJECT_DIR/deploy/app/fishing-firm.service" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "Installation complete. Configure /etc/fishing-firm/fishing-firm.env, then:"
echo "  systemctl start $SERVICE_NAME"
echo "  systemctl status $SERVICE_NAME"
