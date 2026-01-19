#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/remote_controller/server"
OPERATOR_DIR="/opt/remote_controller/operator"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Upload server folder to $APP_DIR before running this script."
  exit 1
fi

if [[ ! -f "$OPERATOR_DIR/index.html" ]]; then
  echo "Operator UI not found at $OPERATOR_DIR/index.html; upload operator/ to serve the web UI."
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  if [[ -f "$APP_DIR/.env.example" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  fi
  echo "Edit $APP_DIR/.env with RC_DATABASE_URL and tokens, then rerun."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker

install -m 644 "$APP_DIR/deploy/remote-controller.service" /etc/systemd/system/remote-controller.service
install -m 644 "$APP_DIR/deploy/remote-controller-healthcheck.service" /etc/systemd/system/remote-controller-healthcheck.service
install -m 644 "$APP_DIR/deploy/remote-controller-healthcheck.timer" /etc/systemd/system/remote-controller-healthcheck.timer
chmod +x "$APP_DIR/deploy/healthcheck.sh"

systemctl daemon-reload
systemctl enable --now remote-controller.service remote-controller-healthcheck.timer

cd "$APP_DIR"
docker compose up -d --build
