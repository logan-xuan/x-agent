# —— 构建一个 **透明、自循环、可追溯** 的 AI Agent 执行系统

> **文档目标**：  
 清晰描述从用户输入到最终输出的完整流程逻辑，涵盖 **LLM 决策、RAG 检索、工具调用、错误恢复、上下文管理与前端流式反馈**。

---

## 📌 一、总体设计原则
workspace/AGENTS.md 是整个agent行为规范总指导流程文件是重要纲领。

| 原则 | 说明 |
|------|------|
| 🔁 **大模型自循环** | LLM 不是一次性调用，而是驱动整个执行流程的核心控制器 |
| 👀 **全程可见** | 所有中间状态实时返回 WebChat，用户清楚知道“AI 在做什么” |
| 🧠 **意图驱动** | 先识别意图 → 再规划任务 → 最后执行 |
| 💡 **智能容错** | 工具失败时自动修正参数并重试 |
| 📦 **模块解耦** | LLM / RAG / Tools / Context 独立但协同工作 |

---

## 🖼️ 二、整体架构图


                [用户通过 WebChat 发送指令]
                          ↓
            +-------------v--------------+
            |        Agent Core Engine      |
            |                               |
    +-------v--------+    +----------v-----------+
    | 意图识别器         |    | 上下文管理器               |
    | (Intent Recognizer) |    | (Context Manager)     |
    +-------+--------+    +----------+-----------+
            |                          |
            v                          v
    +-------v--------+    +----------v-----------+
    | 任务规划器       |    | 记忆系统                |
    | (Planner)      |    | (Memory: md + sqlite-vss)|
    +-------+--------+    +----------+-----------+
            |                          |
            +------------+-----------+
                         ↓
       +-----------------v------------------+
       |         执行调度中心                   |
       | (Orchestrator: LLM 自循环控制)        |
       +-----------------+------------------+
                         ↓
         +---------------v---------------+
         |          决策分支                 |

+---------v----------+ +---------v----------+
 | RAG 增强检索 | | 工具调用与执行 |
 | • hybrid_search() | | • plugin_manager.call() |
 +---------+----------+ +---------+----------+
 | |
 +------------+-----------+
 ↓
 +--------------v---------------+
 | 状态判断 & 错误处理 |
 | • 成功？→ 进入总结阶段 |
 | • 失败？→ 参数修正 → 重新尝试 |
 +--------------+---------------+
 ↓
 +--------------v---------------+
 | LLM 总结生成自然语言回答 |
 | • 注入身份 + 用户画像 + 上下文 |
 +--------------+---------------+
 ↓
 [返回结果至 WebChat UI]
 ↓
 [记录到 MEMORY.md 和 DB]

---

## 🔧 三、核心模块说明

### 1. 【意图识别器】`Intent Recognizer`

- **功能**：将用户自然语言转换为结构化意图
- **输入**：原始文本
- **输出**：JSON 格式的意图对象

```json
{
  "intent": "search",
  "params": {
    "type": "file",
    "query": "项目计划书",
    "location": "Documents"
  }
}

● 实现方式：

    ○ 使用 LLM + JSON mode 解析
    ○ 支持分类：search, remind, create, execute, ask_memory

2. 【上下文管理器】Context Manager
● 功能：构建精简、安全、高效的上下文传给 LLM
● 组成：
    AGENT.md agent 系统总流程 prompt，指导 agent 的工作流，包含其他文件和工具的加载和使用
    SPIRIT.md：Agent 身份设定
    OWNER.md：用户画像
    TOOLS.md: 工具注册表
    压缩后的对话历史（最近 N 轮 + 摘要）
    相关记忆片段（来自 RAG）
    大模型再返回或工具返回的信息
✅ 当会话超过 140 轮时，触发分段压缩机制：

3. 【任务分析器】Task Analyzer（新增）
● 功能：基于规则匹配的任务复杂度分析（无 LLM 调用）
● 输入：用户消息文本
● 输出：TaskAnalysis 对象

```python
@dataclass
class TaskAnalysis:
    complexity: Literal["simple", "complex"]  # 复杂度分级
    confidence: float                          # 置信度
    indicators: list[str]                      # 触发指标
    needs_plan: bool                           # 是否需要计划

● 复杂度判断规则：
    - multi_step: ["先", "然后", "接着", "最后", "步骤", "流程"]
    - conditional: ["如果", "当", "判断", "检查", "验证", "否则"]
    - iteration: ["所有", "每个", "批量", "遍历", "循环", "全部"]
    - uncertainty: ["可能", "或者", "不确定", "试试", "尝试"]
    - scope: ["重构", "迁移", "搭建", "实现", "设计", "构建", "开发"]

● 决策逻辑：
    score = sum(indicator_weights) + length_bonus + sentence_bonus
    if score > 0.6:
        complexity = "complex"
        needs_plan = True

4. 【轻量计划生成器】Light Planner（新增）
● 功能：生成文本格式的执行计划（非结构化 DAG）
● 输入：用户目标 + 可用工具列表
● 输出：文本计划

```text
1. 分析项目目录结构 (工具：list_dir)
2. 查找配置文件 (工具：search_files)
3. 阅读配置内容 (工具：read_file)
4. 修改配置项 (工具：write_file)
5. 验证修改结果 (工具：run_in_terminal)

● 特点：
    - 软引导而非硬约束
    - LLM 可灵活调整执行顺序
    - 低 Token 开销

5. 【计划上下文管理器】Plan Context（新增）
● 功能：追踪计划进度，监控执行状态，触发重规划
● 核心数据结构：

```python
@dataclass
class PlanState:
    original_plan: str           # 原始计划文本
    current_step: int            # 当前步骤 (1-based)
    total_steps: int             # 总步骤数
    completed_steps: list[str]   # 已完成步骤
    failed_count: int            # 连续失败次数
    replan_count: int            # 重规划次数 (防死循环)
    iteration_count: int         # ReAct 迭代次数

● 监控机制：
    a. 每次 tool_result 后更新状态
    b. 检查是否需要重规划：
       - 连续失败 >= 2 次 → 触发
       - 同一步骤卡住 >= 3 轮 → 触发
       - replan_count >= 2 → 停止 (防死循环)
    c. 构建 ReAct 上下文注入 System Prompt

6. 【任务规划器】Planner
● 功能：根据意图拆解成可执行子任务列表
● 示例输入：

"帮我找出上周写的项目计划书"
● 输出任务序列：
[
  { "type": "rag", "action": "hybrid_search", "query": "项目计划书" },
  { "type": "tool", "name": "list_files", "params": { "path": "{{selected_path}}" } },
  { "type": "tool", "name": "read_file", "params": { "path": "{{selected_path}}" } }
]

● 策略：

    ○ 优先使用 RAG 查找已有知识
    ○ 再调用工具获取实时数据或执行操作
    ○ 对于复杂任务，先生成文本计划再执行

7. 【执行调度中心】Orchestrator（LLM 自循环引擎）
这是整个系统的大脑，负责驱动每一步执行。
工作流程：
[开始]
   ↓
→ [任务分析] TaskAnalyzer.analyze()
   ↓
→ {是否需要计划？}
   ├─ 是 → [生成计划] LightPlanner.generate()
   │        ↓
   │     [注入计划到 System Prompt]
   │        ↓
   └─ 否 → [标准 ReAct 流程]
            ↓
→ [LLM 决策]："我需要先做 A"
   ↓
→ [发送 thinking 事件] → 前端显示"正在分析..."
   ↓
→ [执行动作]：调用 RAG 或 Tool
   ↓
→ [捕获结果/错误]
   ↓
→ [更新计划状态] PlanContext.update_from_tool_result()
   ↓
→ [检查是否重规划] PlanContext.should_replan()
   ↓
→ {需要重规划？}
   ├─ 是 → [记录重规划] PlanContext.record_replan()
   │        ↓
   │     [发出 plan_adjustment 事件]
   │        ↓
   └─ 否 → [继续执行]
            ↓
→ [将结果 + 上下文 回传给 LLM]
   ↓
→ [LLM 再决策]："下一步该做 B"
   ↓
→ ... 循环直到完成或达到 max_iterations ...
   ↓
→ [LLM 输出 final_answer]
   ↓
→ [结束]

✅ 实现真正的"大模型自主推理与执行" + "计划引导"。

8. 【RAG 增强检索】
● 功能：从长期记忆中召回相关信息
● 技术栈：
    ○ 向量数据库：sqlite-vss（轻量嵌入）
    ○ 文本匹配：BM25 或关键词提取
    ○ 混合搜索：score = 0.7 * vector + 0.3 * text
● 流程：
    a. 提取查询关键词
    b. 在 MEMORY.md 和 memory.db 中搜索
    c. 返回 top-k 结果作为上下文增强

6. 【工具调用系统】Tools & Plugin System
● 插件目录：plugins/xxx/main.py
● 典型工具：
    ○ web-search：联网搜索
    ○ list_files：列出目录
    ○ create_cron_job：创建定时提醒
    ○ take_photo：拍照（Termux）
    ○ notify：发送通知

7. 【状态判断与错误处理】

● 基础错误处理（ReAct Loop 内置）：
```python
while iteration < max_iterations:
    action = llm_decide_next_step(context)
    
    if action.type == "use_tool":
        result = execute_tool(action.name, action.params)
        
        if not result.success:
            # LLM 自主决定如何修正
            new_params = llm_revise_params(action, result.error)
            context += f"[系统提示：上次调用失败，原因是 {result.error}。请修正参数]"
            retries += 1
            continue
            
        else:
            context += f"[工具返回] {result.output}"
            
    elif action.type == "finish":
        break

✅ 实现"失败 → 修正 → 重试"的闭环。

● 计划监控错误处理（新增）：
```python
# 每次 tool_result 后更新状态
plan_context.update_from_tool_result(state, tool_name, success, output)

# 检查是否需要重规划
need_replan, reason = plan_context.should_replan(state)
if need_replan:
    # 检查是否已达到最大重规划次数
    if state.replan_count >= MAX_REPLAN_COUNT:
        # 停止重规划，返回错误提示
        yield error("已尝试重规划 {n} 次，请简化任务或提供更多信息")
    else:
        # 记录重规划并继续
        plan_context.record_replan(state, reason)
        yield plan_adjustment(reason)

● 防死循环机制：
    - ReAct max_iterations: 5 次
    - 连续失败触发重规划：2 次
    - 卡住触发重规划：3 轮无进展
    - 最大重规划次数：2 次 (防止无限循环)

🔄 四、完整执行流程（以案例说明）

### 场景 1：简单任务（无需计划）

用户输入："今天天气怎么样？"

Step 1️⃣ 任务分析
analysis = TaskAnalyzer.analyze("今天天气怎么样？")
# complexity = "simple"
# needs_plan = False

➡️ 发送：
{
  "event": "task_analysis",
  "data": {
    "complexity": "simple",
    "needs_plan": false
  }
}

Step 2️⃣ 标准 ReAct Loop
迭代 1:
  LLM Thought: "用户询问天气，我需要调用天气 API..."
  Tool Call: web_search("北京今天天气")
  Result: "晴朗，25°C"

迭代 2:
  LLM final_answer: "今天北京天气晴朗，气温 25 摄氏度。"

➡️ 发送 thinking, tool_call, tool_result, final_answer 事件

### 场景 2：复杂多步任务（需要计划）

用户输入："先分析项目结构，然后找到配置文件，最后修改配置项"

Step 1️⃣ 任务分析
analysis = TaskAnalyzer.analyze("先分析项目结构...")
# 关键词匹配："先"、"然后"、"最后" → multi_step 指标
# complexity = "complex"
# needs_plan = True

➡️ 发送：
{
  "event": "task_analysis",
  "data": {
    "complexity": "complex",
    "needs_plan": true,
    "indicators": ["multi_step"]
  }
}

Step 2️⃣ 生成计划
plan_text = LightPlanner.generate(
    goal="先分析项目结构，然后找到配置文件，最后修改配置项",
    tools=["list_dir", "search_files", "read_file", "write_file", "run_in_terminal"]
)

plan_text = """
1. 分析项目目录结构 (工具：list_dir)
2. 查找配置文件 (工具：search_files)
3. 阅读配置内容 (工具：read_file)
4. 修改配置项 (工具：write_file)
5. 验证修改结果 (工具：run_in_terminal)
"""

plan_state = PlanState(
    original_plan=plan_text,
    current_step=1,
    total_steps=5,
    failed_count=0,
    replan_count=0
)

➡️ 发送：
{
  "event": "plan_generated
  "data": {
    "plan": plan_text
  }
}

Step 3️⃣ 注入计划到 System Prompt
system_prompt = f"""
你是一个智能助手...

# 执行计划
【当前计划】
1. 分析项目目录结构 (工具：list_dir) ← 当前步骤
2. 查找配置文件 (工具：search_files)
3. 阅读配置内容 (工具：read_file)
4. 修改配置项 (工具：write_file)
5. 验证修改结果 (工具：run_in_terminal)

【已完成】
(空)

【进度】1/5 (20%)

# 规划提示
按计划逐步执行，如遇到困难可灵活调整。
"""

Step 4️⃣ ReAct Loop 执行（带计划引导）

迭代 1:
  LLM Thought: "根据计划第一步，我需要分析项目结构..."
  Tool Call: list_dir(path="/Users/xuan.lx/Documents/x-agent/x-agent")
  
  ➡️ 发送 thinking, tool_call 事件
  
  Tool Result: "成功：x-agent.db, x-agent.yaml, backend/, frontend/, ..."
  
  ➡️ 监控逻辑触发：
  ```python
  plan_context.update_from_tool_result(
      plan_state,
      tool_name="list_dir",
      success=True,
      output="成功：..."
  )
  # completed_steps: ["list_dir: 成功：..."]
  # current_step: 1 → 2
  
  need_replan, reason = plan_context.should_replan(plan_state)
  # need_replan = False (没有失败)
  ```
  
  ➡️ 发送 tool_result 事件

迭代 2:
  LLM Thought: "计划第二步是查找配置文件..."
  Tool Call: search_files(pattern="*.yaml")
  Result: "成功：x-agent.yaml, backend/x-agent.yaml.example"
  
  ➡️ 状态更新：current_step: 2 → 3
  
  ➡️ 发送 thinking, tool_call, tool_result 事件

迭代 3:
  LLM Thought: "现在读取配置文件..."
  Tool Call: read_file(file_path="x-agent.yaml")
  Result: "失败：文件不存在"
  
  ➡️ 监控逻辑触发：
  ```python
  plan_context.update_from_tool_result(
      plan_state,
      tool_name="read_file",
      success=False,  # 失败！
      output="文件不存在"
  )
  # failed_count: 0 → 1
  
  need_replan, reason = should_replan(plan_state)
  # need_replan = False (failed_count=1 < 2)
  ```
  
  ➡️ 发送 thinking, tool_call, tool_result 事件

迭代 4:
  LLM Thought: "读取失败了，让我试试另一个配置文件..."
  Tool Call: read_file(file_path="backend/x-agent.yaml.example")
  Result: "失败：权限不足"
  
  ➡️ 监控逻辑触发：
  ```python
  # failed_count: 1 → 2
  
  need_replan, reason = should_replan(plan_state)
  # need_replan = True! (failed_count >= 2)
  # reason = "连续失败 2 次"
  
  plan_context.record_replan(plan_state, reason)
  # replan_count: 0 → 1
  # failed_count: 2 → 0 (重置)
  ```
  
  ➡️ 发送：
  {
    "event": "plan_adjustment",
    "data": {
      "reason": "连续失败 2 次"
    }
  }
  
  ➡️ 发送 tool_result 事件

迭代 5:
  LLM 根据新计划继续执行...
  
  ...直到完成或达到 max_iterations...

Step 5️⃣ 总结输出
LLM 综合所有信息生成最终回答。

➡️ 发送 final_answer 事件

Step 6️⃣ 数据归档
● 将本次交互写入 archives/sess_xxx.jsonl
● 关键信息归档至 MEMORY.md 和 sqlite-vss
● 更新计划状态记录

📡 五、WebSocket 流式通信协议

消息格式
{
  "event": "event_type",
  "data": { ... },
  "timestamp": "2025-04-06T10:30:00Z"
}

支持事件类型
event 类型
用途
user_input
用户发送了新消息
task_analysis（新增）
任务复杂度分析结果
thinking
LLM 正在思考下一步
plan_generated, plan_adjustment（新增）
计划生成或调整
planning
任务拆解完成
rag_query
开始 RAG 搜索
rag_result
返回检索结果
tool_call
调用某个工具
tool_result
工具执行结果
error
出错（可恢复）
correction
参数修正
final_answer
最终回答

前端渲染增强（支持计划事件）
```javascript
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  switch (msg.event) {
    case "task_analysis":
      // 显示任务复杂度提示
      if (msg.data.needs_plan) {
        showPlanIndicator("检测到复杂任务，正在生成计划...");
      }
      break;
      
    case "plan_generated's':
      // 展示完整计划
      renderPlan(msg.data.plan);
      break;
      
    case "plan_adjustment":
      // 显示计划调整通知
      showToast(`计划调整：${msg.data.reason}`);
      break;

    case "thinking":
      showTypingIndicator();
      appendBotMessage(msg.data.content, "thinking");
      break;

    case "tool_call":
      logToolCall(msg.data.name);
      break;

    case "final_answer":
      hideTyping();
      displayFinalAnswer(msg.data.content);
      break;
  }
};
```

✅ 七、优势总结

维度
效果
🔍 透明性
用户看得见每一步进展 + 计划状态
🧠 智能性
LLM 驱动全流程 + 计划引导
🛠️ 可靠性
错误自动修复 + 重规划机制
📊 可追溯性
所有事件可回放分析 + 计划历史
💬 交互友好
回答更自然、更有温度 + 进度可见
⚙️ 扩展性强
插件化支持新增能力 + 计划模板
🎯 任务成功率
简单任务快速响应 + 复杂任务有计划保障
⚡ 性能优化
低 Token 开销 + 防死循环机制