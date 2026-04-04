#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/pm2-common.sh"

echo "🛑 使用 pm2 停止 X-Agent 服务..."
pm2_cmd delete x-agent-backend x-agent-frontend >/dev/null 2>&1 || true

echo "📋 当前 pm2 状态:"
pm2_cmd status
