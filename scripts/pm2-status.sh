#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/pm2-common.sh"

echo "📋 pm2 进程状态"
pm2_cmd status x-agent-backend x-agent-frontend

echo ""
echo "📋 健康检查"
if backend_healthcheck; then
  echo "   后端 ($XAGENT_BACKEND_PORT): ✅"
else
  echo "   后端 ($XAGENT_BACKEND_PORT): ❌"
fi

if frontend_healthcheck; then
  echo "   前端 ($XAGENT_FRONTEND_PORT): ✅"
else
  echo "   前端 ($XAGENT_FRONTEND_PORT): ❌"
fi
