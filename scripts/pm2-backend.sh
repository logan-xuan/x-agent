#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/pm2-common.sh"

ensure_pm2_home
ensure_config_file
mkdir -p "$BACKEND_DIR/logs"

BACKEND_HOST="$(read_server_config "host" "0.0.0.0")"
BACKEND_PORT="$(read_server_config "port" "8888")"
ensure_backend_port_available "$BACKEND_PORT"

cd "$BACKEND_DIR"
export PYTHONUNBUFFERED=1

echo "PM2 启动后端: http://$BACKEND_HOST:$BACKEND_PORT"

if [ -n "${X_AGENT_PYTHON:-}" ]; then
    exec "$X_AGENT_PYTHON" -m src.main
fi

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
    exec "$BACKEND_DIR/.venv/bin/python" -m src.main
fi

if [ -x "$BACKEND_DIR/venv/bin/python" ]; then
    exec "$BACKEND_DIR/venv/bin/python" -m src.main
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run python -m src.main
fi

if command -v python3 >/dev/null 2>&1; then
    exec python3 -m src.main
fi

if command -v python >/dev/null 2>&1; then
    exec python -m src.main
fi

echo "未找到可用的 Python 解释器，请设置 X_AGENT_PYTHON 或先创建 backend/.venv" >&2
exit 1
