#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.tmp/voice-tunnel/localhost-run.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No running voice tunnel PID file found."
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  rm -f "$PID_FILE"
  echo "Removed stale PID file."
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped tunnel PID $PID"
else
  echo "Tunnel PID $PID is not running."
fi

rm -f "$PID_FILE"
