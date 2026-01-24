#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/remote_controller/server"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Upload server folder to $APP_DIR before running this script."
  exit 1
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ -f "$APP_DIR/.env.example" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  fi
  echo "Edit $APP_DIR/.env with tokens and database settings, then rerun."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
sed -i '/download.docker.com/d' /etc/apt/sources.list || true
rm -f /etc/apt/sources.list.d/docker.list || true
apt-get update
apt-get install -y docker.io docker-compose-plugin
systemctl enable --now docker

install -m 644 "$APP_DIR/deploy/systemd/remote-controller.service" /etc/systemd/system/remote-controller.service
install -m 644 "$APP_DIR/deploy/systemd/remote-controller-healthcheck.service" /etc/systemd/system/remote-controller-healthcheck.service
install -m 644 "$APP_DIR/deploy/systemd/remote-controller-healthcheck.timer" /etc/systemd/system/remote-controller-healthcheck.timer
chmod +x "$APP_DIR/deploy/scripts/healthcheck.sh"

systemctl daemon-reload
systemctl enable --now remote-controller.service remote-controller-healthcheck.timer

cd "$APP_DIR"
docker compose --env-file "$APP_DIR/.env" -f "$APP_DIR/deploy/docker/docker-compose.yml" up -d --build
