#!/bin/bash
#
# X-Agent 服务重启脚本
#
# 用途: 停止所有现有服务并重新启动
# 从配置文件中读取端口设置
# 作者: X-Agent Team
#

# 不使用 set -e，手动处理错误以避免意外退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 切换到脚本所在目录
cd "$SCRIPT_DIR"

echo "🔄 开始重启 X-Agent 服务..."
echo "📁 工作目录: $SCRIPT_DIR"

# 从配置文件读取端口
CONFIG_FILE="backend/x-agent.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 配置文件不存在: $CONFIG_FILE"
    echo "💡 请先复制示例配置文件: cd backend && cp x-agent.yaml.example x-agent.yaml"
    exit 1
fi

BACKEND_PORT=$(grep -E "^\s*port:" "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d ' ' 2>/dev/null)
if [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT=8888
fi

FRONTEND_PORT=$(grep -E "^\s*frontend_port:" "$CONFIG_FILE" | awk '{print $2}' | tr -d ' ' 2>/dev/null)
if [ -z "$FRONTEND_PORT" ]; then
    FRONTEND_PORT=5173
fi

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
pkill -f "node.*frontend" 2>/dev/null || true

# 短暂等待进程退出
sleep 1

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
echo "⏳ 等待端口释放..."
sleep 2

# 验证端口已释放
if lsof -i :"$BACKEND_PORT" >/dev/null 2>&1; then
    echo "⚠️  后端端口 $BACKEND_PORT 仍被占用，服务可能无法正常启动"
fi

if lsof -i :"$FRONTEND_PORT" >/dev/null 2>&1; then
    echo "⚠️  前端端口 $FRONTEND_PORT 仍被占用，服务可能无法正常启动"
fi

echo "✅ 旧服务已停止"

# 启动后端服务
echo ""
echo "======================================"
echo "🚀 启动后端服务..."
echo "======================================"
"$SCRIPT_DIR/start-backend.sh"
BACKEND_RESULT=$?

if [ $BACKEND_RESULT -ne 0 ]; then
    echo "❌ 后端服务启动失败，请检查日志: backend/logs/backend.log"
fi

# 等待后端启动
echo "⏳ 等待后端服务初始化..."
sleep 4

# 启动前端服务
echo ""
echo "======================================"
echo "🚀 启动前端服务..."
echo "======================================"
"$SCRIPT_DIR/start-frontend.sh"
FRONTEND_RESULT=$?

if [ $FRONTEND_RESULT -ne 0 ]; then
    echo "❌ 前端服务启动失败，请检查日志: frontend/frontend.log"
fi

# 等待前端启动
sleep 2

# 最终状态检查
echo ""
echo "======================================"
echo "🎉 X-Agent 服务重启完成！"
echo "======================================"
echo ""
echo "📋 服务状态:"

# 检查后端服务
BACKEND_STATUS="❌ 未运行"
if lsof -i :"$BACKEND_PORT" >/dev/null 2>&1; then
    # 进一步验证：尝试访问健康检查端点
    if curl -s "http://localhost:$BACKEND_PORT/api/v1/health" > /dev/null 2>&1; then
        BACKEND_STATUS="✅ 运行中"
    else
        BACKEND_STATUS="⚠️  端口监听但服务未就绪"
    fi
fi

# 检查前端服务
FRONTEND_STATUS="❌ 未运行"
if lsof -i :"$FRONTEND_PORT" >/dev/null 2>&1; then
    # 进一步验证：尝试访问前端页面
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$FRONTEND_PORT/" 2>/dev/null | grep -q "200"; then
        FRONTEND_STATUS="✅ 运行中"
    else
        FRONTEND_STATUS="⚠️  端口监听但响应异常"
    fi
fi

echo "   后端服务 ($BACKEND_PORT): $BACKEND_STATUS"
echo "   前端服务 ($FRONTEND_PORT): $FRONTEND_STATUS"
echo ""
echo "🌐 访问地址:"
echo "   后端 API:  http://localhost:$BACKEND_PORT"
echo "   前端界面:  http://localhost:$FRONTEND_PORT"
echo "   Agent界面: http://localhost:$FRONTEND_PORT/agent"
echo ""
echo "📄 日志文件:"
echo "   后端日志: backend/logs/backend.log"
echo "   前端日志: frontend/frontend.log"
echo ""