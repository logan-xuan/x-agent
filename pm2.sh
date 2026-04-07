#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECOSYSTEM_FILE="$SCRIPT_DIR/ecosystem.config.cjs"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/scripts/pm2-common.sh"

ensure_pm2_home

COMMAND="${1:-status}"
ENV_NAME="${2:-production}"

usage() {
    cat <<'EOF'
用法:
  ./pm2.sh start [production|development]
  ./pm2.sh restart [production|development]
  ./pm2.sh stop
  ./pm2.sh status
  ./pm2.sh logs [x-agent-backend|x-agent-frontend] [lines]

说明:
  - 默认环境为 production
  - PM2_HOME 固定到仓库内 .pm2，避免和全局 PM2 实例冲突
EOF
}

validate_env() {
    case "${1:-production}" in
        production|development) ;;
        *)
            echo "不支持的环境: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
}

start_apps() {
    local env_name="$1"
    validate_env "$env_name"
    cd "$SCRIPT_DIR"
    pm2 startOrReload "$ECOSYSTEM_FILE" --env "$env_name" --update-env
    pm2 save
    pm2 status x-agent-backend x-agent-frontend
}

restart_apps() {
    local env_name="$1"
    validate_env "$env_name"
    cd "$SCRIPT_DIR"
    pm2 startOrReload "$ECOSYSTEM_FILE" --env "$env_name" --update-env
    pm2 save
    pm2 status x-agent-backend x-agent-frontend
}

stop_apps() {
    cd "$SCRIPT_DIR"
    pm2 delete x-agent-frontend >/dev/null 2>&1 || true
    pm2 delete x-agent-backend >/dev/null 2>&1 || true
    pm2 save --force >/dev/null 2>&1 || true
    pm2 status
}

show_logs() {
    local target="${1:-}"
    local lines="${2:-100}"

    case "$target" in
        "" )
            pm2 logs --lines "$lines"
            ;;
        x-agent-backend|x-agent-frontend)
            pm2 logs "$target" --lines "$lines"
            ;;
        *)
            echo "不支持的日志目标: $target" >&2
            usage >&2
            exit 1
            ;;
    esac
}

case "$COMMAND" in
    start)
        start_apps "$ENV_NAME"
        ;;
    restart)
        restart_apps "$ENV_NAME"
        ;;
    stop)
        stop_apps
        ;;
    status)
        pm2 status x-agent-backend x-agent-frontend
        ;;
    logs)
        show_logs "${2:-}" "${3:-100}"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "不支持的命令: $COMMAND" >&2
        usage >&2
        exit 1
        ;;
esac
