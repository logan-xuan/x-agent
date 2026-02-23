#!/bin/bash
#
# X-Agent 前端服务启动脚本
#
# 用途: 启动 X-Agent 前端服务
# 从 vite.config.ts 中读取端口配置
# 作者: X-Agent Team
#

set -e  # 遇到错误时退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "🚀 启动 X-Agent 前端服务..."

# 检查前端目录是否存在
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

# 读取Vite配置文件中的端口，默认5173
VITE_CONFIG="$FRONTEND_DIR/vite.config.ts"
DEFAULT_PORT=5173

# 如果配置文件存在，则尝试从中读取端口
if [ -f "$VITE_CONFIG" ]; then
    PORT=$(grep -E "port:" "$VITE_CONFIG" | grep -oE '[0-9]+' | head -1)
fi

if [ -z "$PORT" ]; then
    PORT=$DEFAULT_PORT
    echo "⚠️  未在配置文件中找到端口设置，使用默认端口: $PORT"
else
    echo "📋 从配置文件读取前端端口: $PORT"
fi

# 检查端口是否被占用
if lsof -i :"$PORT" >/dev/null 2>&1; then
    echo "⚠️  端口 $PORT 被占用，正在停止相关进程..."
    lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# 进入前端目录并启动服务
cd "$FRONTEND_DIR"

# 检查是否已安装依赖
if [ ! -d "node_modules" ]; then
    echo "📦 检测到未安装依赖，正在安装..."
    npm install
fi

echo "🔧 使用 npm 启动前端开发服务器..."
echo "🔌 前端服务将在 http://localhost:$PORT 启动"

# 启动前端服务
nohup npm run dev > frontend.log 2>&1 &

# 获取后台进程PID
FRONTEND_PID=$!

if [ $FRONTEND_PID ]; then
    echo "✅ 前端服务已启动，PID: $FRONTEND_PID"
    echo "🌐 访问地址: http://localhost:$PORT"
    echo "📄 日志文件: $FRONTEND_DIR/frontend.log"
else
    echo "❌ 前端服务启动失败"
    exit 1
fi

# 等待一段时间以确保服务完全启动
sleep 3

# 验证服务是否正在运行
if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo "✅ 前端服务运行正常"
else
    echo "❌ 前端服务未能成功启动，请检查日志文件"
    exit 1
fi

echo "✨ 前端服务启动完成！"