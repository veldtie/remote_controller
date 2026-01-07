#!/usr/bin/env bash
set -euo pipefail

cd /opt/remote_controller/server

container_id=$(/usr/bin/docker compose ps -q signaling 2>/dev/null || true)
if [[ -z "$container_id" ]]; then
  /usr/bin/docker compose up -d signaling
  exit 0
fi

status=$(/usr/bin/docker inspect -f '{{.State.Health.Status}}' "$container_id" 2>/dev/null || echo "missing")

if [[ "$status" == "healthy" || "$status" == "starting" ]]; then
  exit 0
fi

/usr/bin/docker compose up -d signaling
