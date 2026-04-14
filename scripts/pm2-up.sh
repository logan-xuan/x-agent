#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/pm2-common.sh"

echo "🚀 使用 pm2 启动 X-Agent 服务..."
echo "📁 Root: $XAGENT_ROOT_DIR"
echo "🏠 PM2_HOME: $PM2_HOME"
echo "🐍 Python: $XAGENT_PYTHON"
echo "🔌 Backend port: $XAGENT_BACKEND_PORT"
echo "🔌 Frontend port: $XAGENT_FRONTEND_PORT"

pm2_cmd delete x-agent-backend x-agent-frontend >/dev/null 2>&1 || true

pm2_cmd start "$XAGENT_ECOSYSTEM_FILE" --only x-agent-backend,x-agent-frontend --update-env
pm2_cmd save >/dev/null 2>&1 || true

echo "⏳ 等待服务启动..."
sleep 2

backend_ok=0
frontend_ok=0

for _ in $(seq 1 20); do
  if backend_healthcheck; then
    backend_ok=1
    break
  fi
  sleep 1
done

for _ in $(seq 1 20); do
  if frontend_healthcheck; then
    frontend_ok=1
    break
  fi
  sleep 1
done

echo ""
echo "📋 pm2 状态:"
pm2_cmd status x-agent-backend x-agent-frontend

echo ""
echo "📋 健康检查:"
if [ "$backend_ok" -eq 1 ]; then
  echo "   后端 ($XAGENT_BACKEND_PORT): ✅"
else
  echo "   后端 ($XAGENT_BACKEND_PORT): ❌"
fi

if [ "$frontend_ok" -eq 1 ]; then
  echo "   前端 ($XAGENT_FRONTEND_PORT): ✅"
else
  echo "   前端 ($XAGENT_FRONTEND_PORT): ❌"
fi

if [ "$backend_ok" -ne 1 ] || [ "$frontend_ok" -ne 1 ]; then
  echo ""
  echo "❌ 至少一个服务未通过健康检查"
  exit 1
fi

echo ""
echo "✅ pm2 启动完成"
