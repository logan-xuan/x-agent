#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/backend/x-agent.yaml"

export XAGENT_ROOT_DIR="$ROOT_DIR"
export PM2_HOME="$ROOT_DIR/.pm2"

mkdir -p "$PM2_HOME"

backend_port_from_config() {
  if [ -f "$CONFIG_FILE" ]; then
    grep -E "^\s*port:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d ' ' || true
  fi
}

frontend_port_from_config() {
  if [ -f "$CONFIG_FILE" ]; then
    grep -E "^\s*frontend_port:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d ' ' || true
  fi
}

resolve_python_bin() {
  if [ -f "/Users/xuan.lx/miniconda3/bin/python" ]; then
    echo "/Users/xuan.lx/miniconda3/bin/python"
    return
  fi
  if [ -f "$ROOT_DIR/backend/.venv/bin/python" ]; then
    echo "$ROOT_DIR/backend/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "python3"
}

resolve_pm2_bin() {
  if command -v pm2 >/dev/null 2>&1; then
    command -v pm2
    return
  fi

  local npm_prefix=""
  npm_prefix="$(npm config get prefix 2>/dev/null || true)"
  if [ -n "$npm_prefix" ] && [ -x "$npm_prefix/bin/pm2" ]; then
    echo "$npm_prefix/bin/pm2"
    return
  fi

  if [ -x "$HOME/.npm-global/bin/pm2" ]; then
    echo "$HOME/.npm-global/bin/pm2"
    return
  fi

  echo "pm2"
}

export XAGENT_BACKEND_PORT="${XAGENT_BACKEND_PORT:-$(backend_port_from_config)}"
export XAGENT_FRONTEND_PORT="${XAGENT_FRONTEND_PORT:-$(frontend_port_from_config)}"
export XAGENT_BACKEND_PORT="${XAGENT_BACKEND_PORT:-8888}"
export XAGENT_FRONTEND_PORT="${XAGENT_FRONTEND_PORT:-5177}"
export XAGENT_PYTHON="${XAGENT_PYTHON:-$(resolve_python_bin)}"
export XAGENT_PM2_BIN="${XAGENT_PM2_BIN:-$(resolve_pm2_bin)}"
export XAGENT_ECOSYSTEM_FILE="$ROOT_DIR/ecosystem.config.js"

ensure_pm2_available() {
  if [ ! -x "$XAGENT_PM2_BIN" ]; then
    echo "❌ pm2 不可用: $XAGENT_PM2_BIN"
    exit 1
  fi
}

pm2_cmd() {
  ensure_pm2_available
  "$XAGENT_PM2_BIN" "$@"
}

backend_healthcheck() {
  curl -fsS -L "http://localhost:${XAGENT_BACKEND_PORT}/api/v1/health/" >/dev/null
}

frontend_healthcheck() {
  curl -fsS "http://localhost:${XAGENT_FRONTEND_PORT}/" >/dev/null
}
