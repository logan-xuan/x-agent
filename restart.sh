#!/bin/bash
#
# X-Agent 服务重启脚本
#
# 用途: 停止所有现有服务并重新启动
# 从配置文件中读取端口设置
# 作者: X-Agent Team
#

set -e  # 遇到错误时退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔄 开始重启 X-Agent 服务..."

# 获取端口配置
BACKEND_PORT=$(grep -E "^  port:" backend/x-agent.yaml | head -1 | awk '{print $2}' 2>/dev/null || echo '8000')
FRONTEND_PORT=5173  # 前端通常在5173端口

echo "📋 端口配置 - 后端: $BACKEND_PORT, 前端: $FRONTEND_PORT"

# 停止现有服务
echo "🛑 正在停止现有服务..."

# 停止后端进程 (Python相关的X-Agent进程)
pkill -f "python.*src.main" 2>/dev/null || true
pkill -f "uvicorn.*x_agent" 2>/dev/null || true
pkill -f "python.*-m.*src.main" 2>/dev/null || true

# 停止前端进程 (Vite/React开发服务器)
pkill -f "vite" 2>/dev/null || true
pkill -f "npm.*dev" 2>/dev/null || true

# 关闭占用端口的进程
if lsof -i :"$BACKEND_PORT" >/dev/null 2>&1; then
    echo "⚠️  端口 $BACKEND_PORT 仍然被占用，强制关闭..."
    lsof -ti:"$BACKEND_PORT" | xargs kill -9 2>/dev/null || true
fi

if lsof -i :"$FRONTEND_PORT" >/dev/null 2>&1; then
    echo "⚠️  端口 $FRONTEND_PORT 仍然被占用，强制关闭..."
    lsof -ti:"$FRONTEND_PORT" | xargs kill -9 2>/dev/null || true
fi

# 等待端口释放
sleep 3

echo "✅ 旧服务已停止"

# 更新依赖（如果需要）
echo "📦 检查并更新依赖..."

# 更新后端依赖
if [ -d "backend" ]; then
    cd backend
    if [ -f "pyproject.toml" ]; then
        echo "🔄 更新后端依赖..."
        pip install -e . > /dev/null 2>&1 || echo "⚠️  后端依赖更新可能存在问题，请检查"
    fi
    cd ..
fi

# 更新前端依赖
if [ -d "frontend" ]; then
    cd frontend
    if [ -f "package.json" ]; then
        echo "🔄 更新前端依赖..."
        npm install > /dev/null 2>&1 || echo "⚠️  前端依赖更新可能存在问题，请检查"
    fi
    cd ..
fi

# 启动后端服务
echo "🚀 启动后端服务..."
"$SCRIPT_DIR/start-backend.sh"

# 等待后端启动
sleep 5

# 启动前端服务
echo "🚀 启动前端服务..."
"$SCRIPT_DIR/start-frontend.sh"

# 等待前端启动
sleep 3

echo ""
echo "🎉 X-Agent 服务重启完成！"
echo ""
echo "📋 服务状态:"
BACKEND_STATUS="❌"
FRONTEND_STATUS="❌"

if lsof -i :"$BACKEND_PORT" >/dev/null 2>&1; then
    BACKEND_STATUS="✅"
fi

if lsof -i :"$FRONTEND_PORT" >/dev/null 2>&1; then
    FRONTEND_STATUS="✅"
fi

echo "   后端服务 ($BACKEND_PORT): $BACKEND_STATUS"
echo "   前端服务 ($FRONTEND_PORT): $FRONTEND_STATUS"
echo ""
echo "🌐 访问地址:"
echo "   后端 API: http://localhost:$BACKEND_PORT"
echo "   前端界面: http://localhost:$FRONTEND_PORT"
echo ""