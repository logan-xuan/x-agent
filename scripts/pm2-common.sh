#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
CONFIG_FILE="${X_AGENT_CONFIG_FILE:-$BACKEND_DIR/x-agent.yaml}"
PM2_HOME_DEFAULT="$REPO_ROOT/.pm2"

ensure_backend_dir() {
    if [ ! -d "$BACKEND_DIR" ]; then
        echo "backend 目录不存在: $BACKEND_DIR" >&2
        exit 1
    fi
}

ensure_frontend_dir() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo "frontend 目录不存在: $FRONTEND_DIR" >&2
        exit 1
    fi
}

ensure_config_file() {
    ensure_backend_dir
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "配置文件不存在: $CONFIG_FILE" >&2
        echo "请先执行: cd backend && cp x-agent.yaml.example x-agent.yaml" >&2
        exit 1
    fi
}

read_server_config() {
    local key="$1"
    local default_value="$2"
    local value=""

    value="$(
        awk -v key="$key" '
            /^server:/ { in_server=1; next }
            in_server && /^[^[:space:]]/ { exit }
            in_server && $1 == key ":" {
                print $2
                exit
            }
        ' "$CONFIG_FILE" | tr -d "\"'\r "
    )"

    if [ -n "$value" ]; then
        printf '%s\n' "$value"
    else
        printf '%s\n' "$default_value"
    fi
}

ensure_frontend_deps() {
    ensure_frontend_dir
    cd "$FRONTEND_DIR"

    if [ -d "node_modules" ]; then
        return 0
    fi

    if [ -f "package-lock.json" ]; then
        echo "未检测到 node_modules，执行 npm ci..."
        npm ci
    else
        echo "未检测到 node_modules，执行 npm install..."
        npm install
    fi
}

ensure_pm2_home() {
    export PM2_HOME="${PM2_HOME:-$PM2_HOME_DEFAULT}"
    mkdir -p "$PM2_HOME"
}

ensure_backend_port_available() {
    local port="$1"
    local pids
    pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"

    if [ -z "$pids" ]; then
        return 0
    fi

    for pid in $pids; do
        local cmd cwd
        cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        cwd="$(
            lsof -a -p "$pid" -d cwd -Fn 2>/dev/null \
            | sed -n 's/^n//p' \
            | tail -n 1
        )"

        if [[ "$cwd" == "$BACKEND_DIR"* ]] || [[ "$cmd" == *"-m src.main"* ]] || [[ "$cmd" == *"uvicorn"* && "$cmd" == *"src.main:app"* ]]; then
            echo "检测到旧的 X-Agent 后端占用端口 $port (pid=$pid)，正在停止..."
            kill "$pid" >/dev/null 2>&1 || true

            for _ in {1..20}; do
                if ! kill -0 "$pid" >/dev/null 2>&1; then
                    break
                fi
                sleep 0.5
            done

            if kill -0 "$pid" >/dev/null 2>&1; then
                echo "进程 $pid 未在超时内退出，执行强制停止"
                kill -9 "$pid" >/dev/null 2>&1 || true
            fi
        else
            echo "端口 $port 已被其他进程占用，拒绝启动后端" >&2
            echo "pid=$pid" >&2
            echo "command=$cmd" >&2
            echo "cwd=$cwd" >&2
            exit 1
        fi
    done
}
