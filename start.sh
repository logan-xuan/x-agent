#!/bin/bash
#
# X-Agent 全栈服务启动脚本
#
# 用途: 同时启动后端和前端服务
# 从 x-agent.yaml 和 vite.config.ts 中读取端口配置
# 作者: X-Agent Team
#

set -e  # 遇到错误时退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 开始启动 X-Agent 全栈服务..."

# 启动后端服务
echo "=== 启动后端服务 ==="
"$SCRIPT_DIR/start-backend.sh"

# 等待后端启动
sleep 5

# 启动前端服务
echo "=== 启动前端服务 ==="
"$SCRIPT_DIR/start-frontend.sh"

echo ""
echo "🎉 X-Agent 全栈服务启动完成！"
echo ""
echo "📋 服务访问地址:"
echo "   后端 API: $(grep -E '^  port:' backend/x-agent.yaml | head -1 | awk '{print $2}' 2>/dev/null || echo '8000')"
echo "   前端界面: 5173 (默认)"
echo ""
echo "💡 访问指南:"
echo "   - API 测试: http://localhost:8000/api/v1/health"
echo "   - 前端界面: http://localhost:5173"
echo "   - WebSocket: ws://localhost:8000/ws/chat"
echo ""