#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/pm2-common.sh"

ensure_pm2_home
ensure_config_file
ensure_frontend_deps

FRONTEND_HOST="${PM2_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="$(read_server_config "frontend_port" "5177")"
BACKEND_PORT="$(read_server_config "port" "8888")"
FRONTEND_MODE="${PM2_FRONTEND_SERVE_MODE:-preview}"

cd "$FRONTEND_DIR"
export VITE_PORT="$FRONTEND_PORT"
export VITE_API_URL="${VITE_API_URL:-http://localhost:$BACKEND_PORT}"
export VITE_WS_URL="${VITE_WS_URL:-ws://localhost:$BACKEND_PORT}"

echo "PM2 启动前端: http://$FRONTEND_HOST:$FRONTEND_PORT ($FRONTEND_MODE)"

case "$FRONTEND_MODE" in
    preview)
        npm run build
        exec npm run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
        ;;
    dev)
        exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
        ;;
    *)
        echo "不支持的 PM2_FRONTEND_SERVE_MODE: $FRONTEND_MODE，可选值: preview / dev" >&2
        exit 1
        ;;
esac
