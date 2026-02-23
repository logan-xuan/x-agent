#!/bin/bash
#
# X-Agent 后端服务启动脚本
#
# 用途: 启动 X-Agent 后端服务
# 从 x-agent.yaml 中读取端口配置
# 作者: X-Agent Team
#

set -e  # 遇到错误时退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "🚀 启动 X-Agent 后端服务..."

# 检查后端目录是否存在
if [ ! -d "$BACKEND_DIR" ]; then
    echo "❌ 后端目录不存在: $BACKEND_DIR"
    exit 1
fi

# 读取配置文件中的端口
CONFIG_FILE="$BACKEND_DIR/x-agent.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 配置文件不存在: $CONFIG_FILE"
    echo "💡 请先复制示例配置文件: cp x-agent.yaml.example x-agent.yaml"
    exit 1
fi

# 从配置文件提取端口，默认8000
PORT=$(grep -E "^  port:" "$CONFIG_FILE" | head -1 | awk '{print $2}' 2>/dev/null)
if [ -z "$PORT" ]; then
    PORT=8000
    echo "⚠️  未在配置文件中找到端口设置，使用默认端口: $PORT"
else
    echo "📋 从配置文件读取后端端口: $PORT"
fi

# 检查端口是否被占用
if lsof -i :"$PORT" >/dev/null 2>&1; then
    echo "⚠️  端口 $PORT 被占用，正在停止相关进程..."
    lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# 进入后端目录并启动服务
cd "$BACKEND_DIR"

echo "🔧 使用 Python 启动后端服务..."
PYTHON_PATH=""
# 尝试使用虚拟环境中的Python
if [ -f ".venv/bin/python" ]; then
    PYTHON_PATH=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_PATH="venv/bin/python"
else
    PYTHON_PATH="python"
fi

echo "🐍 使用 Python 解释器: $PYTHON_PATH"
echo "🔌 后端服务将在 http://localhost:$PORT 启动"

# 启动后端服务
nohup $PYTHON_PATH -m src.main > backend.log 2>&1 &

# 获取后台进程PID
BACKEND_PID=$!

if [ $BACKEND_PID ]; then
    echo "✅ 后端服务已启动，PID: $BACKEND_PID"
    echo "🌐 访问地址: http://localhost:$PORT"
    echo "📄 日志文件: $BACKEND_DIR/backend.log"
else
    echo "❌ 后端服务启动失败"
    exit 1
fi

# 等待一段时间以确保服务完全启动
sleep 3

# 验证服务是否正在运行
if kill -0 $BACKEND_PID 2>/dev/null; then
    echo "✅ 后端服务运行正常"
else
    echo "❌ 后端服务未能成功启动，请检查日志文件"
    exit 1
fi

echo "✨ 后端服务启动完成！"