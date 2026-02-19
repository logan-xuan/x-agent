#!/bin/bash
#
# X-Agent 服务重启脚本
#
# 用途: 停止现有服务并启动新实例
# 作者: Claude for X-Agent
# 日期: 2026-02-17
#

set -e  # 遇到错误时退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "🔄 开始重启 X-Agent 服务..."

# 停止现有服务
echo "🛑 正在停止现有服务..."
pkill -f "python.*uvicorn.*src.main" 2>/dev/null || true
pkill -f "python -m src.main" 2>/dev/null || true
sleep 2

# 检查端口是否被占用
if lsof -i :8000 >/dev/null 2>&1; then
    echo "⚠️  端口 8000 仍然被占用，尝试强制关闭..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
fi

# 等待端口释放
sleep 2

# 启动后端服务
echo "🚀 启动后端服务..."
cd "$BACKEND_DIR"
nohup python -m src.main > backend.log 2>&1 &
BACKEND_PID=$!

if [ $BACKEND_PID ]; then
    echo "✅ 后端服务已启动，PID: $BACKEND_PID"
else
    echo "❌ 后端服务启动失败"
    exit 1
fi

# 检查前端是否正在运行
if ! lsof -i :5173 >/dev/null 2>&1; then
    echo "💡 前端服务似乎未运行，如需启动请手动执行: cd frontend && npm run dev"
else
    echo "✅ 前端服务已在运行，端口: 5173"
fi

# 等待一段时间以确保服务完全启动
sleep 3

# 检查后端服务状态
if kill -0 $BACKEND_PID 2>/dev/null; then
    echo "✅ 后端服务正在运行，监听端口: 8000"
    echo "🌐 访问地址: http://localhost:8000"
else
    echo "❌ 后端服务未能成功启动，请检查 backend.log 文件"
    exit 1
fi

echo "✨ 服务重启完成！"
echo ""
echo "📋 服务状态:"
echo "   后端: http://localhost:8000 (PID: $BACKEND_PID)"
if lsof -i :5173 >/dev/null 2>&1; then
    echo "   前端: http://localhost:5173"
fi
echo ""
echo "📄 日志文件: $BACKEND_DIR/backend.log"
echo ""
echo "💡 提示: 修改 policy_parser.py 和 policy_engine.py 的 P0 级别段落识别功能已生效"