#!/usr/bin/env bash
set -euo pipefail

# Change these addresses/networks to your lab network.
ADMIN_NET="192.168.56.0/24"
APP_IP="192.168.56.10"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root."
  exit 1
fi

apt-get update
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ADMIN_NET" to any port 22 proto tcp comment 'SSH administration'
ufw allow from "$APP_IP" to any port 5432 proto tcp comment 'PostgreSQL only from app server'
ufw --force enable
ufw status verbose
