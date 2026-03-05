#!/bin/bash
# 杀掉占用 8888 端口的后端进程（仅 Python/uvicorn），为 debugpy 调试腾出端口
# 不会影响前端服务

PORT=8888

# 只查找 Python 进程（uvicorn 是 python 启动的）
PIDS=$(lsof -ti:$PORT -sTCP:LISTEN 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "✅ 端口 $PORT 没有进程占用，可以直接启动 debugpy"
    exit 0
fi

# 逐个检查，只杀 python/uvicorn 相关进程
KILLED=0
for PID in $PIDS; do
    CMD=$(ps -p "$PID" -o comm= 2>/dev/null)
    if [[ "$CMD" == *python* ]] || [[ "$CMD" == *uvicorn* ]]; then
        echo "🛑 杀掉后端进程: PID=$PID ($CMD)"
        kill -9 "$PID" 2>/dev/null
        KILLED=$((KILLED + 1))
    else
        echo "⏭️  跳过非后端进程: PID=$PID ($CMD)"
    fi
done

if [ $KILLED -gt 0 ]; then
    echo "✅ 已清理 $KILLED 个后端进程，可以用 debugpy 启动了"
else
    echo "⚠️  端口 $PORT 上没有找到 Python 进程"
fi
