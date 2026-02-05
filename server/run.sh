#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/docker/docker-compose.yml"
PROJECT_DIR="$ROOT_DIR/deploy/docker"
COMPOSE_CMD=(docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE")

if [[ -f "$ROOT_DIR/.env" ]]; then
  COMPOSE_CMD+=(--env-file "$ROOT_DIR/.env")
fi

if [[ $# -gt 0 ]]; then
  "${COMPOSE_CMD[@]}" "$@"
else
  "${COMPOSE_CMD[@]}" up -d --build
fi
