#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/remote_controller/server"
OPERATOR_DIR="/opt/remote_controller/operator"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Missing $APP_DIR. Upload server folder first."
  exit 1
fi

if [[ ! -f "$OPERATOR_DIR/index.html" ]]; then
  echo "Operator UI not found at $OPERATOR_DIR/index.html; upload operator/ to serve the web UI."
fi

install -m 644 "$APP_DIR/deploy/remote-controller.service" /etc/systemd/system/remote-controller.service
install -m 644 "$APP_DIR/deploy/remote-controller-healthcheck.service" /etc/systemd/system/remote-controller-healthcheck.service
install -m 644 "$APP_DIR/deploy/remote-controller-healthcheck.timer" /etc/systemd/system/remote-controller-healthcheck.timer
chmod +x "$APP_DIR/deploy/healthcheck.sh"

systemctl daemon-reload
systemctl restart remote-controller.service
systemctl restart remote-controller-healthcheck.timer

cd "$APP_DIR"
docker compose up -d --build
