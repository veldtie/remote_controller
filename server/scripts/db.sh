#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/docker/docker-compose.yml"
SERVICE_NAME="postgres"
COMPOSE_CMD=(docker compose --project-directory "$ROOT_DIR" -f "$COMPOSE_FILE")

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +a
fi

DB_USER="${RC_DB_USER:-rc_user}"
DB_NAME="${RC_DB_NAME:-remote_controller}"

command="${1:-}"

case "$command" in
  start)
    "${COMPOSE_CMD[@]}" up -d "$SERVICE_NAME"
    ;;
  stop)
    "${COMPOSE_CMD[@]}" stop "$SERVICE_NAME"
    ;;
  restart)
    "${COMPOSE_CMD[@]}" restart "$SERVICE_NAME"
    ;;
  status)
    "${COMPOSE_CMD[@]}" ps "$SERVICE_NAME"
    ;;
  logs)
    "${COMPOSE_CMD[@]}" logs -f --tail=100 "$SERVICE_NAME"
    ;;
  psql)
    "${COMPOSE_CMD[@]}" exec -it "$SERVICE_NAME" psql -U "$DB_USER" -d "$DB_NAME"
    ;;
  shell)
    "${COMPOSE_CMD[@]}" exec -it "$SERVICE_NAME" sh
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|psql|shell}"
    exit 1
    ;;
esac
