#!/usr/bin/env bash
set -euo pipefail

project_dir="/opt/remote_controller/server"
compose_file="$project_dir/deploy/docker/docker-compose.yml"
compose_cmd=(/usr/bin/docker compose --project-directory "$project_dir" -f "$compose_file")
cd "$project_dir"

container_id=$("${compose_cmd[@]}" ps -q signaling 2>/dev/null || true)
if [[ -z "$container_id" ]]; then
  "${compose_cmd[@]}" up -d signaling
  exit 0
fi

status=$(/usr/bin/docker inspect -f '{{.State.Health.Status}}' "$container_id" 2>/dev/null || echo "missing")

if [[ "$status" == "healthy" || "$status" == "starting" ]]; then
  exit 0
fi

"${compose_cmd[@]}" up -d signaling
