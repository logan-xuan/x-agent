# —— 构建一个 **透明、自循环、可追溯** 的 AI Agent 执行系统

> **文档目标**：  
> 面向开发者与架构师，清晰描述从用户输入到最终输出的完整流程逻辑，涵盖 **LLM 决策、RAG 检索、工具调用、错误恢复、上下文管理与前端流式反馈**。

---

## 📌 一、总体设计原则

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
    SOUL.md：Agent 身份设定
    USER.md：用户画像
    tool.md: 工具注册表
    压缩后的对话历史（最近 N 轮 + 摘要）
    相关记忆片段（来自 RAG）
    大模型再返回或工具返回的信息
✅ 当会话超过 140 轮时，触发分段压缩机制：

3. 【任务规划器】Planner
● 功能：根据意图拆解成可执行子任务列表
● 示例输入：

“帮我找出上周写的项目计划书”
● 输出任务序列：
[
  { "type": "rag", "action": "hybrid_search", "query": "项目计划书" },
  { "type": "tool", "name": "list_files", "params": { "path": "~/Documents" } },
  { "type": "tool", "name": "read_file", "params": { "path": "{{selected_path}}" } }
]

● 策略：

    ○ 优先使用 RAG 查找已有知识
    ○ 再调用工具获取实时数据或执行操作

4. 【执行调度中心】Orchestrator（LLM 自循环引擎）
这是整个系统的大脑，负责驱动每一步执行。
工作流程：
[开始]
   ↓
→ [LLM 决策]：“我需要先做 A”
   ↓
→ [发送 thinking 事件] → 前端显示“正在分析...”
   ↓
→ [执行动作]：调用 RAG 或 Tool
   ↓
→ [捕获结果/错误]
   ↓
→ [将结果 + 上下文 回传给 LLM]
   ↓
→ [LLM 再决策]：“下一步该做 B”
   ↓
→ ... 循环直到完成 ...
   ↓
→ [LLM 输出 final_answer]
   ↓
→ [结束]

✅ 实现真正的“大模型自主推理与执行”。

5. 【RAG 增强检索】
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
while not task_done and retries < MAX_RETRIES:
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

✅ 实现“失败 → 修正 → 重试”的闭环。

🔄 四、完整执行流程（以案例说明）
场景：用户输入
“帮我找出上周写的项目计划书”

Step 1️⃣ 接收输入 & 初始化
session_id = "sess_abc123"
user_input = "帮我找出上周写的项目计划书"


Step 2️⃣ 意图识别
{
  "intent": "search",
  "params": {
    "type": "file",
    "keywords": ["项目计划书"],
    "time_range": "last_week"
  }
}

➡️ WebSocket 发送：
{
  "event": "thinking",
  "data": {
    "content": "我需要查找你上周创建的‘项目计划书’相关文件"
  }
}


Step 3️⃣ 任务规划
[
  { "type": "rag", "query": "项目计划书" },
  { "type": "tool", "name": "list_files", "params": { "path": "~/Documents", "filter": "project.*plan.*" } }
]

➡️ 发送：
{
  "event": "planning",
  "data": {
    "steps": [...]
  }
}


Step 4️⃣ 执行 RAG 检索
results = hybrid_search("项目计划书")

➡️ 发送：
{ "event": "rag_query", "data": { "query": "项目计划书" } }

➡️ 发送：
{
  "event": "rag_result",
  "data": {
    "results": [...],
    "scores": [...]
  }
}


Step 5️⃣ 调用工具：list_files
tool_result = plugin_manager.call_plugin(
  name="list_files",
  data={"path": "~/Documents", "pattern": ".*(计划书|proposal).*"}
)

➡️ 发送：
{
  "event": "tool_call",
  "data": {
    "name": "list_files",
    "params": { ... }
  }
}

➡️ 发送：
{
  "event": "tool_result",
  "data": {
    "success": true,
    "output": ["plan_v1.md", "draft.docx"]
  }
}


Step 6️⃣ LLM 再决策 → 是否继续？
LLM 判断是否已足够信息来回答：
“我已经找到了两个候选文件：plan_v1.md 和 draft.docx，它们都在 Documents 目录下。”
➡️ 发送：
{
  "event": "thinking",
  "data": {
    "content": "已找到两个可能的目标文件..."
  }
}


Step 7️⃣ 总结输出
LLM 综合所有信息生成最终回答：
“找到了！你在上周于 Documents 文件夹中保存了两个名为 ‘plan_v1.md’ 和 ‘draft.docx’ 的文件，可能是你要找的项目计划书。”
➡️ 发送：
{
  "event": "final_answer",
  "data": {
    "content": "找到了！你在上周于 Documents 文件夹中保存了两个名为 ‘plan_v1.md’ 和 ‘draft.docx’ 的文件，可能是你要找的项目计划书。"
  }
}


Step 8️⃣ 数据归档
● 将本次交互写入 archives/sess_abc123.jsonl
● 关键信息归档至 MEMORY.md 和 sqlite-vss

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
thinking
LLM 正在思考下一步
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

🧩 六、前端 WebChat 渲染逻辑
const ws = new WebSocket("/ws/chat");

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  switch (msg.event) {
    case "thinking":
      showTypingIndicator();
      appendBotMessage(msg.data.content, "thinking");
      break;

    case "planning":
      renderTaskList(msg.data.steps);
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


✅ 七、优势总结
维度
效果
🔍 透明性
用户看得见每一步进展
🧠 智能性
LLM 驱动全流程，非脚本化
🛠️ 可靠性
错误自动修复，不轻易失败
📊 可追溯性
所有事件可回放分析
💬 交互友好
回答更自然、更有温度
⚙️ 扩展性强
插件化支持新增能力