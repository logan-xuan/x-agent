#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT_DIR/.tmp/voice-tunnel"
LOG_FILE="$STATE_DIR/localhost-run.log"
PID_FILE="$STATE_DIR/localhost-run.pid"
CONFIG_FILE="$ROOT_DIR/backend/x-agent.yaml"
LOCAL_PORT="${LOCAL_PORT:-8888}"
SSH_CMD="${SSH_CMD:-ssh}"
PYTHON_CMD="${PYTHON_CMD:-}"
RELOAD_CONFIG="${RELOAD_CONFIG:-1}"
RELOAD_URL="${RELOAD_URL:-http://127.0.0.1:${LOCAL_PORT}/api/v1/config/reload}"
PUBLIC_HEALTH_PATH="${PUBLIC_HEALTH_PATH:-/api/v1/health/}"
PUBLIC_HEALTH_TIMEOUT="${PUBLIC_HEALTH_TIMEOUT:-20}"

mkdir -p "$STATE_DIR"

if [[ -z "$PYTHON_CMD" ]]; then
  if [[ -x "/Users/xuan.lx/miniconda3/bin/python" ]]; then
    PYTHON_CMD="/Users/xuan.lx/miniconda3/bin/python"
  elif [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
    PYTHON_CMD="$ROOT_DIR/backend/.venv/bin/python"
  else
    PYTHON_CMD="python3"
  fi
fi

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${EXISTING_PID}" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "Tunnel already running with PID $EXISTING_PID"
    echo "Stop it first or remove $PID_FILE if stale."
    exit 1
  fi
  rm -f "$PID_FILE"
fi

: > "$LOG_FILE"

"$SSH_CMD" \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -R "80:localhost:${LOCAL_PORT}" \
  nokey@localhost.run \
  >"$LOG_FILE" 2>&1 &

TUNNEL_PID=$!
echo "$TUNNEL_PID" > "$PID_FILE"

cleanup() {
  if kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

trap cleanup INT TERM

PUBLIC_HOST=""
for _ in $(seq 1 30); do
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "Tunnel process exited unexpectedly. Log:"
    cat "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi

  if grep -Eq 'https://[A-Za-z0-9._-]+' "$LOG_FILE"; then
    PUBLIC_HOST="$(python3 - <<'PY' "$LOG_FILE"
from pathlib import Path
import re
import sys

content = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
matches = re.findall(r'tunneled with tls termination,\s+(https://[A-Za-z0-9._-]+)', content)
print(matches[-1] if matches else "")
PY
)"
    [[ -n "$PUBLIC_HOST" ]] && break
  fi
  sleep 1
done

if [[ -z "$PUBLIC_HOST" ]]; then
  echo "Failed to detect public host. Log:"
  cat "$LOG_FILE"
  cleanup
  exit 1
fi

PUBLIC_BASE_URL="${PUBLIC_HOST}/api/v1/assets/audio"
HEALTHCHECK_STATUS="skipped"
if command -v curl >/dev/null 2>&1; then
  HEALTHCHECK_URL="${PUBLIC_HOST}${PUBLIC_HEALTH_PATH}"
  HEALTHCHECK_DEADLINE=$((SECONDS + PUBLIC_HEALTH_TIMEOUT))
  while (( SECONDS < HEALTHCHECK_DEADLINE )); do
    HTTP_CODE="$(curl --silent --output /dev/null --write-out '%{http_code}' "$HEALTHCHECK_URL" || true)"
    if [[ "$HTTP_CODE" == "200" ]]; then
      HEALTHCHECK_STATUS="ok"
      break
    fi
    sleep 1
  done
  if [[ "$HEALTHCHECK_STATUS" != "ok" ]]; then
    echo "Public tunnel healthcheck failed for $HEALTHCHECK_URL"
    echo "Last HTTP code: ${HTTP_CODE:-unavailable}"
    echo "Tunnel log:"
    cat "$LOG_FILE"
    cleanup
    exit 1
  fi
else
  HEALTHCHECK_STATUS="curl-missing"
fi

"$PYTHON_CMD" "$ROOT_DIR/scripts/update_voice_public_base_url.py" "$PUBLIC_BASE_URL" --config "$CONFIG_FILE" >/dev/null

RELOAD_STATUS="skipped"
if [[ "$RELOAD_CONFIG" == "1" ]]; then
  if command -v curl >/dev/null 2>&1; then
    if curl --silent --show-error --fail -X POST "$RELOAD_URL" >/dev/null; then
      RELOAD_STATUS="ok"
    else
      RELOAD_STATUS="failed"
    fi
  else
    RELOAD_STATUS="curl-missing"
  fi
fi

echo "Tunnel PID: $TUNNEL_PID"
echo "Public host: $PUBLIC_HOST"
echo "Tunnel healthcheck: $HEALTHCHECK_STATUS"
echo "voice.public_base_url => $PUBLIC_BASE_URL"
echo "Config reload: $RELOAD_STATUS"
if [[ "$RELOAD_STATUS" == "failed" ]]; then
  echo "Manual fallback: curl -X POST $RELOAD_URL"
fi
echo "Log file: $LOG_FILE"
echo "Press Ctrl+C to stop the tunnel."

wait "$TUNNEL_PID"
cleanup
