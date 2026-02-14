# 设计目标
当 AI Agent 执行长任务时，如果没有反馈机制，用户会怀疑它“卡住”或“崩溃”了
现在我们来设计心跳设计，主要是确保agent在执行长任务时，能监控其存活状态。
构建一个高可用、可监控、用户友好的长任务执行系统
适用于：RAG 检索、代码生成与运行、多步规划、文件处理等耗时操作
实现方式
1,防止“无响应”错觉
主动发送周期性心跳信号
2,监控 Agent 存活状态
心跳超时即判定为“死亡”
3,提升用户体验
显示“正在思考…”、“已检索3个文档”等进度
4,支持中断与恢复
用户可在任意时刻取消任务
5,日志可追溯
所有心跳记录用于调试和分析

# 心跳机制设计文档


## 整体架构图
                     +------------------+
                     |     前端 UI       |
                     | (WebChat / App)  |
                     +--------+---------+
                              ↓ ↑
                   [Heartbeat Event Stream]
                              ↓ ↑
          +------------------v------------------+
          |           Agent 执行引擎             |
          |                                     |
   +------v-------+    +----------v----------+   |
   | 心跳发射器      |    | 任务执行上下文        |   |
   | (Emitter)     |<-->| (ExecutionContext)|   |
   +------^-------+    +----------+----------+   |
          |                        |              |
          |                        ↓（调用）       |
          |             +----------v-----------+   |
          |             | 工具链 / 子任务         |   |
          |             | (Tools, Subtasks)   |   |
          |             +---------------------+   |
          |                                     |
          +------------+  心跳存储与监控           |
                       | (Storage & Monitor)   |
                       +------------------------+



## 核心组件设计
### 【心跳定义】Heartbeat 消息结构
{
  "session_id": "sess_abc123",
  "task_id": "task_gen_code_456",
  "status": "running", 
  "phase": "retrieving_documents",
  "progress": 0.4,
  "message": "正在从知识库中检索相关文档…（3/7）",
  "timestamp": "2025-04-06T10:30:00Z",
  "ttl": 30  // 存活时间（秒），用于服务端判断是否离线
}

status 取值：
● "pending"：等待启动
● "running"：运行中
● "paused"：暂停
● "success"：成功完成
● "error"：出错
● "cancelled"：被用户取消
phase 示例：
● "planning"
● "searching_knowledge"
● "executing_command"
● "generating_code"

### 【心跳发射器】Heartbeat Emitter
#### heartbeat/emitter.py
import time
from typing import Callable
import threading

class HeartbeatEmitter:
    def __init__(self, send_fn: Callable, interval=3):
        self.send_fn = send_fn  # 发送到前端的方式（如 WebSocket.send）
        self.interval = interval
        self.running = False
        self.thread = None

    def start(self, task_info: dict):
        self.running = True
        self.task_info = task_info

        def loop():
            while self.running:
                heartbeat = {
                    **self.task_info,
                    "status": "running",
                    "timestamp": time.time(),
                    "ttl": self.interval * 3
                }
                try:
                    self.send_fn(heartbeat)
                except Exception as e:
                    print(f"⚠️ 心跳发送失败: {e}")
                time.sleep(self.interval)

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def update(self, **kwargs):
        """动态更新 phase / progress / message"""
        self.task_info.update(kwargs)

    def stop(self, final_status="success", message=None):
        if message:
            self.task_info["message"] = message
        self.task_info["status"] = final_status
        self.send_fn(self.task_info)
        self.running = False


### 【任务执行上下文】ExecutionContext
#### agent/context.py
from .emitter import HeartbeatEmitter
import uuid

class ExecutionContext:
    def __init__(self, session_id: str, send_heartbeat: Callable):
        self.session_id = session_id
        self.task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.emitter = HeartbeatEmitter(send_heartbeat)
        self.is_cancelled = False

    def start_task(self, name: str, total_steps: int = None):
        self.emitter.start({
            "session_id": self.session_id,
            "task_id": self.task_id,
            "name": name,
            "phase": "init",
            "progress": 0,
            "message": f"开始执行: {name}"
        })

    def update_phase(self, phase: str, message: str, step=None, total=None):
        progress = None
        if step is not None and total:
            progress = step / total
        self.emitter.update(phase=phase, message=message, progress=progress)

    def done(self, result: str):
        self.emitter.stop("success", result)

    def error(self, msg: str):
        self.emitter.stop("error", msg)

    def cancel(self):
        self.is_cancelled = True
        self.emitter.stop("cancelled", "任务已被用户取消")


### 【Agent 中集成心跳】
#### agent/main.py
def run_long_task(user_query: str, ctx: ExecutionContext):
    try:
        ctx.start_task("generate_solution", total_steps=5)

        # Step 1: 分析需求
        ctx.update_phase("analyzing", "正在理解你的问题...", 1, 5)
        time.sleep(2)

        # Step 2: 检索记忆
        ctx.update_phase("retrieving", "正在查找相关知识...", 2, 5)
        relevant = hybrid_search(user_query)
        ctx.update_phase("retrieving", f"找到 {len(relevant)} 条相关记忆", 2.5, 5)

        # Step 3: 规划步骤
        ctx.update_phase("planning", "正在制定解决方案步骤...", 3, 5)
        plan = llm_plan(user_query, relevant)

        if ctx.is_cancelled:
            return

        # Step 4: 执行工具链
        ctx.update_phase("executing", "正在执行第1步...", 4, 5)
        for i, step in enumerate(plan):
            if ctx.is_cancelled:
                break
            ctx.update_phase("executing", f"执行: {step}", 4 + i * 0.2, 5)
            execute_step(step)

        # Step 5: 输出结果
        ctx.update_phase("finalizing", "正在整理最终回答...", 5, 5)
        response = generate_final_answer()
        ctx.done(response)

    except Exception as e:
        ctx.error(str(e))


### 【前端接收心跳】WebSocket 流式渲染
// frontend/chat.js
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "heartbeat") {
    const taskBar = document.getElementById("task-status");
    
    // 更新进度条
    taskBar.innerHTML = `
      <div class="phase">${data.phase}</div>
      <div class="msg">${data.message}</div>
      <progress value="${data.progress || 0}" max="1"></progress>
    `;

    // 超时检测（客户端也可做）
    resetTimeout(data.task_id);
  }

  if (data.status === "success") {
    appendMessage("assistant", data.message);
    hideTaskBar();
  }
};


## 超时与存活监控机制
### 服务端监控（防僵尸任务）
#### monitor.py
import time
from threading import Thread

active_tasks = {}  # task_id -> last_heartbeat_time

def cleanup_dead_tasks():
    now = time.time()

    dead = [ ]

    for tid, hb_time in active_tasks.items():
        if now - hb_time > 60:  # 超过60秒无心跳
            dead.append(tid)
    for tid in dead:
        force_kill_task(tid)
        del active_tasks[tid]

# 后台守护线程
Thread(target=lambda: while True; cleanup_dead_tasks(); time.sleep(10), daemon=True).start()


## 心跳策略建议
场景
推荐间隔
说明
简单任务（<10s）
不需要
或只发开始/结束
中等任务（10~60s）
3~5 秒
显示进度条
长任务（>60s）
2~3 秒
支持取消按钮
批量处理任务
按批次触发
如“已完成第3批”
💡 小技巧：首次延迟更短（如1秒），让用户立刻感知到响应。

# 优势总结
维度
效果
 用户体验
再也不会觉得“AI 卡住了”
 系统可观测性
所有任务状态一目了然
 故障排查
心跳日志帮助定位卡点
 安全控制
支持主动取消，避免失控
 可恢复性
结合 checkpoint 可实现断点续传

# 进阶扩展方向
功能
实现思路
 任务仪表盘
展示所有 session 的当前任务状态
 死亡告警
自动通知开发者“Agent 失联”
 Checkpoint 恢复
心跳中包含中间状态，支持重启后继续
 多 Agent 协作
每个子 agent 发送自己的心跳
 日志归档
将心跳流写入 .log.jsonl 用于回放

