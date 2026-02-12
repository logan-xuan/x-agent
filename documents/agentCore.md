# 需求
构建一个支持 LLM + Tools + MCP + SubAgent 协同工作的智能执行中枢
让 AI Agent 不再是“单打独斗”，而是成为一个会调用工具、能分解任务、可协调子代理的智能指挥官。

# 一、设计目标
能力
实现方式
✅ 任务自动规划与拆解
使用 LLM 进行推理分解
✅ 工具（Tools）动态调用
白名单管理，安全执行 CLI / API
✅ MCP（Model Control Protocol）集成
支持结构化输出、函数调用、JSON mode
✅ SubAgent 分工协作
多专家并行处理不同子任务
✅ 上下文共享与同步
所有参与者共用压缩后上下文
✅ 心跳监控存活状态
长任务不卡死，用户看得见进度
✅ 异常回滚与恢复机制
出错时自动降级或请求人工干预

# 二、整体架构图
                     +------------------+
                     |   用户输入        |
                     | "帮我分析项目风险" |
                     +--------+---------+
                              ↓
          +------------------v------------------+
          |           Agent Core 执行引擎         |
          |                                       |
  +-------v--------+    +------------v-----------+ 
  | 任务规划器       |    | 上下文管理器               |
  | (Planner)      |    | (Context Manager)     |
  +-------+--------+    +------------+-----------+
          |                          |
          v                          v
+---------v-------------+    +-------v--------------+
| 工具选择器               |    | 记忆系统                |
| (Tool Selector)       |    | (Memory: md + sqlite-vss)|
+---------+-------------+    +-------+--------------+
          |                          |
          v                          v
+---------v-------------+    +-------v--------------+
| MCP 控制层              |    | 子代理调度器              |
| (Function Calling /    |    | (SubAgent Orchestrator) |
|  JSON Mode)           |    +-----------+------------+
+---------+-------------+                |
          |                              |
          v                              v
+---------v-------------+    +-----------v------------+
| 本地/远程工具执行         |    | 并行子代理：              |
| • CLI                  |    | • Researcher           |
| • Web Search           |    | • Coder                |
| • File Ops             |    | • Reviewer             |
+------------------------+    +------------------------+

          ↑_________________________________________↓
                              共享：压缩上下文 + 心跳通信 + 审计日志


# 三、核心模块详解
## 1. 【任务规划器】Planner
class Planner:
    def plan(self, goal: str, context: str) -> List[Task]:
        prompt = f"""
        请将以下目标拆解为一系列可执行的子任务。要求：
        - 每个任务必须明确、可验证
        - 优先使用工具或子代理完成
        - 输出格式为 JSON 列表

        示例：
        目标：写一篇关于AI伦理的文章
        → [
          {{"type": "research", "topic": "AI ethics principles"}},
          {{"type": "tool", "name": "web-search", "query": "Asilomar AI Principles"}},
          {{"type": "agent", "role": "writer", "task": "撰写初稿"}}
        ]

        当前目标：{goal}
        上下文摘要：{context[:500]}
        
        拆解结果：
        """
        result = llm_json_mode(prompt)
        return parse_tasks(result)

支持 type: tool | agent | mcp | human_confirm

## 2. 【上下文管理器】ContextManager
● 自动加载：

    ○ SOUL.md, USER.md
    ○ 最近两天日志
    ○ MEMORY.md（长期记忆）
● 触发压缩（>140轮）
● 提供混合检索接口
ctx = ContextManager()
compressed = ctx.compress(session_id, full_history)


## 3. 【工具选择器】ToolSelector
class ToolSelector:
    def select(self, task: Task) -> Optional[Tool]:
        if task.type == "shell":
            return trusted_cli_tool
        elif "search" in task.topic:
            return web_search_tool
        elif "file" in task.name:
            return file_tool
        return None

✅ 支持自动绑定参数、权限检查、审计记录

## 4. 【MCP 层】Model Control Protocol 支持
类似 Anthropic 的 tool use 或 OpenAI 的 function calling
### 定义工具 schema
tools_schemas = [
  {
    "name": "execute_local_command",
    "description": "在安全范围内执行本地命令",
    "input_schema": {
      "type": "object",
      "properties": {
        "command_id": {"type": "string"},
        "params": {"type": "object"}
      }
    }
  },
  {
    "name": "spawn_subagent",
    "description": "启动特定角色的子代理",
    "input_schema": {
      "type": "object",
      "properties": {
        "role": {"type": "string", "enum": ["researcher", "coder", "reviewer"]},
        "task": {"type": "string"}
      }
    }
  }
]

### 调用 LLM 启用 MCP 模式
response = llm.invoke(
  prompt,
  tools=tools_schemas,
  tool_choice="auto"
)

 解析调用
for tool_call in response.tool_calls:
    handle_tool_call(tool_call)


## 5. 【子代理调度器】SubAgentOrchestrator
class SubAgentOrchestrator:
    AGENTS = {
        "researcher": ResearcherAgent(),
        "coder": CodeAgent(),
        "reviewer": ReviewerAgent(),
        "executor": ExecutorAgent()
    }

    def run_parallel(self, tasks: List[Task]) -> Dict:
        results = {}
        heartbeat = HeartbeatEmitter(send_fn)

        for task in tasks:
            role = task.get("role", "general")
            agent = self.AGENTS.get(role)

            # 注入共享上下文
            agent.context = self.shared_context

            # 异步执行
            def worker(t, a):
                try:
                    result = a.run(t.task)
                    results[t.id] = result
                except Exception as e:
                    results[t.id] = {"error": str(e)}

            thread = threading.Thread(target=worker, args=(task, agent))
            thread.start()

        # 等待完成或超时
        wait_with_heartbeat(heartbeat, len(tasks))

        return results


## 6. 【执行流程主干】AgentCore.run()
class AgentCore:
    def run(self, user_input: str, session_id: str):
        # Step 1: 加载并压缩上下文
        history = load_session_history(session_id)
        compressed_ctx = ContextManager().compress(history)

        # Step 2: 规划任务
        goal = user_input
        tasks = Planner().plan(goal, compressed_ctx)

        # Step 3: 初始化执行环境
        executor = SubAgentOrchestrator()
        executor.shared_context = compressed_ctx
        heartbeat = HeartbeatEmitter(...).start(task_info)

        final_result = ""

        for task in tasks:
            heartbeat.update(phase=f"processing-{task.type}")

            if task.type == "tool":
                tool = ToolSelector().select(task)
                result = tool._run(task.params)
            elif task.type == "agent":
                result = executor.spawn(task.role, task)
            elif task.type == "human_confirm":
                show_confirmation_modal(task.preview)
                wait_for_user()
                result = "confirmed"
            else:
                # 默认由主 LLM 处理
                result = llm.invoke(f"{compressed_ctx}\n继续处理：{task.desc}")

            final_result += "\n" + result

            # 更新上下文（用于后续任务）
            compressed_ctx = update_context(compressed_ctx, result)

        # Step 4: 返回结果 + 归档
        heartbeat.done(final_result)
        MemoryManager().log_final_result(session_id, final_result)

        return final_result


# 四、协作模式示例
场景：用户提问：“帮我写一个 Python 脚本分析日志”
执行流程：
步骤
参与者
动作
1
Planner
拆解为：① 查找日志格式 ② 编写脚本 ③ 添加错误处理
2
SubAgent.Orchestrator
分派给 researcher 和 coder 并行执行
3
researcher
使用 web-search 工具查找常见日志结构
4
coder
使用 file-write 工具生成 analyze_log.py
5
reviewer
调用 pylint 工具检查代码质量
6
main agent
汇总结果返回用户，并归档到 MEMORY.md
 实现了真正的“团队协作”。

# 五、优势总结
特性
效果
 智能规划
把复杂问题变成分步行动
 工具联动
CLI / 文件 / 搜索自动调用
 多代理协同
不同角色各司其职
 MCP 支持
结构化输出，避免幻觉
 心跳可见
长任务不再失联
 上下文压缩
始终轻量高效
 全程审计
所有行为可追溯


