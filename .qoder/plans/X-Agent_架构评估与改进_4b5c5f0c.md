
# X-Agent 系统架构评估与改进方案

---

## 一、系统架构总览

X-Agent 采用 **四层分层架构 + Port/Adapter 核心设计**：

```
API & Endpoints Layer (WebSocket / REST / SSE / Channel)
        ↓
Gateway Layer (Envelope 统一信封 → Dispatcher 分发 → AgentBridge 编排)
        ↓
Agent Core Layer (双层循环 + Port/Adapter + Hook 生命周期)
        ↓
Infrastructure Layer (Memory / LLM Router / Storage / Skills / Cron)
```

核心文件：
- 入口：`backend/src/main.py` (473行, 9步启动序列)
- Agent 循环：`backend/src/agent_core/agent_loop.py` (662行, 双层循环)
- Gateway 分发：`backend/src/gateway/dispatcher.py` (513行)
- Agent 桥接：`backend/src/gateway/agent_bridge.py` (798行)
- 9 个 Port 接口定义：`backend/src/agent_core/ports/`
- Hook 系统：`backend/src/agent_core/hooks.py` (272行)

---

## 二、优秀设计（值得保持和加强）

### 2.1 Port/Adapter 解耦架构 (9/10)

Agent Core 层实现了**零外部依赖**，通过 9 个 Protocol 接口（LLMPort, ToolPort, MemoryPort, SkillPort, ContextPort, SystemPromptPort, PlanPort, LoggerPort）定义边界，所有外部交互由 Adapter 实现注入。

**优势**：
- 核心循环可独立测试，无需 mock 外部服务
- 更换 LLM 提供商只需新增 Adapter，不碰核心代码
- 依赖方向单向（外层依赖内层），无循环依赖风险

### 2.2 Gateway Envelope 统一信封 (8.5/10)

所有渠道（WebSocket/REST/CLI/钉钉/Telegram）的消息统一封装为 `Envelope`，Gateway 层实现**协议无关性**。

**优势**：
- 新增渠道只需实现 Envelope 适配，不影响业务逻辑
- Agent 路由支持 `agent_id > agent_name > DEFAULT` 优先级
- 请求追踪 trace_id 贯穿全链路

### 2.3 双层循环 + 流式事件模型 (8.5/10)

外层处理 follow-up 消息，内层处理 tool calls + steering，通过 AsyncGenerator 产出 10 种事件类型，支持中断和接管。

### 2.4 Memory 混合搜索 (8/10)

结合向量搜索（ONNX 嵌入 + 余弦相似度）和关键词搜索（BM25），权重 6:4 融合，支持三种写入模式（历史总结/自动压缩/直接写入）+ 文件监听同步。

### 2.5 配置热重载能力 (8/10)

`x-agent.yaml` 修改无需重启，SPIRIT.md / MEMORY.md 等上下文文件通过 FileWatcher 自动同步。LLM 路由支持一主多备 + 熔断降级。

### 2.6 全链路可观测性 (7.5/10)

结构化日志（JSON, structlog）、Trace ID 追踪、AgentLogger 持久化（文件轮转）、前端 Trace 可视化（ReactFlow）。

---

## 三、不足与问题分析

### 3.1 多 Agent 协作能力薄弱 (严重)

**现状**：
- 有配置驱动的多 Agent 定义（`x-agent.yaml` 中 `multi_agent.agents`）
- 有 Identity 层级支持（MAIN/PARTNER/SUB + `derive()` 派生）
- 但 **无显式的 Agent-to-Agent 消息 API**
- Agent 间协作仅通过 SkillPort 间接实现（技能派发）

**问题**：
- 无法实现 Agent A 向 Agent B 发送消息并等待响应
- 无任务委派和结果回传机制
- 无 Agent 生命周期管理（启动/停止/健康检查）
- 无共享状态或黑板（blackboard）机制

### 3.2 Prompt 构建缺乏动态扩展能力 (中等)

**现状**：
- SystemPromptPort 存在但功能单一，主要是静态拼接
- Hook 系统已定义 `BEFORE_LLM_CALL` 可修改 prompt
- 但缺少**结构化的 Prompt 组装管道**（插件式片段注入）

**问题**：
- 添加新的 prompt 片段（如安全规则、角色增强、上下文注入）需要修改 Adapter 代码
- 无优先级排序机制，多个 Hook 修改 prompt 时顺序不确定
- 无 prompt 片段的启用/禁用/条件触发控制

### 3.3 Tool 调用缺少 Hook 扩展点 (中等)

**现状**：
- Hook 系统已有 `BEFORE_TOOL_EXEC` 和 `AFTER_TOOL_EXEC`
- 但缺少**工具选择阶段**的 Hook（LLM 决定调用哪些工具之前）
- 无工具调用审批/拦截机制（高危工具）
- 无工具结果转换/增强 Hook

### 3.4 定时任务稳定性问题 (中等)

**现状**：
- 基于 APScheduler 4.0（alpha 版本）
- CronScheduler 使用 Singleton 模式
- `_job_history` 无界增长存在内存泄漏风险

**问题**：
- APScheduler 4.0 是 alpha 版本，稳定性存疑
- 任务失败后无自动重试策略
- 无任务链（Job A → Job B）支持
- 无分布式调度能力
- Cron 作业的 Agent 执行粒度过粗（整个会话级别）

### 3.5 Conversation 模块耦合度高 (中等)

`conversation` 与 `gateway` 存在双向依赖：
- `gateway` 依赖 `conversation` 的 AgentContext, Identity
- `conversation` 的 DAO 被 `gateway` 间接调用
- Identity 应分离为独立值对象模块

### 3.6 测试覆盖不均 (中等)

- Memory 系统覆盖好（~80-90%）
- Gateway 分发逻辑（~30%）、CLI（0%）、前端（0%）覆盖严重不足
- 无 API 端点集成测试
- 配置热重载无测试验证

### 3.7 错误处理不一致 (轻微)

部分模块抛出自定义异常，部分返回错误值，缺少统一的错误分类和恢复策略。

---

## 四、面向未来扩展的改进方案

### Task 1: Agent-to-Agent 通信能力

**目标**：实现 Agent 间的显式通信、任务委派和协同工作。

**设计方案**：

```
                    AgentBus (中央消息总线)
                   /        |         \
              Agent A    Agent B    Agent C
              (Main)    (Research)  (Code)
```

**核心组件**：

1. **AgentBus（Agent 消息总线）**
   - 位置：新建 `backend/src/agent_core/agent_bus.py`
   - 职责：Agent 间消息路由、请求-响应匹配、超时管理
   - 消息类型：`AgentRequest`（请求）、`AgentResponse`（响应）、`AgentNotification`（单向通知）

2. **AgentRegistry（Agent 注册中心）**
   - 位置：新建 `backend/src/services/agent_registry.py`
   - 职责：Agent 生命周期管理、能力注册、健康检查
   - 每个 Agent 注册时声明能力标签（capabilities）

3. **DelegatePort（委派端口）**
   - 位置：新增 Port `backend/src/agent_core/ports/delegate_port.py`
   - 核心方法：`delegate(target_agent_id, task, timeout)` → `DelegateResult`
   - Agent Core 循环中可通过此 Port 调用其他 Agent

4. **协作模式**：
   - **请求-响应**：Agent A delegate 给 Agent B，等待结果
   - **广播通知**：Agent A 通知所有相关 Agent 某事件发生
   - **任务链**：Agent A → Agent B → Agent C 链式执行
   - **并行分发**：Agent A 同时 delegate 给 B 和 C，汇总结果

**Identity 增强**：
   - 现有 `parent_trace_id` 字段已为嵌套调用预留
   - 新增 `delegation_chain: list[str]` 记录委派链路
   - 新增 `shared_context_id: str` 支持共享上下文空间

---

### Task 2: 动态 Prompt 构建 / Prompt Hook 扩展

**目标**：实现插件式 prompt 组装管道，支持动态片段注入和条件控制。

**设计方案**：

```
PromptPipeline
  ├─ SystemSection (基础人设, priority=0)
  ├─ IdentitySection (身份信息, priority=10)
  ├─ MemorySection (记忆注入, priority=20)
  ├─ ToolSection (工具说明, priority=30)
  ├─ SafetySection (安全规则, priority=40, conditional)
  ├─ ExperienceSection (经验注入, priority=50, conditional)
  └─ CustomSections (用户自定义, priority=60+)
```

**核心组件**：

1. **PromptSection（Prompt 片段）**
   - 位置：新建 `backend/src/agent_core/prompt/section.py`
   - 属性：`name, priority, content_fn, condition_fn, enabled`
   - `content_fn(context) -> str`：动态生成内容
   - `condition_fn(context) -> bool`：条件触发

2. **PromptPipeline（组装管道）**
   - 位置：新建 `backend/src/agent_core/prompt/pipeline.py`
   - 职责：按 priority 排序，过滤 condition，拼装最终 prompt
   - 支持 token 预算管理：各 section 声明 max_tokens，pipeline 自动裁剪

3. **PromptHook 扩展**：
   - 在现有 HookPoint 基础上新增：
     - `BEFORE_PROMPT_BUILD`：prompt 构建前，可注入/移除 section
     - `AFTER_PROMPT_BUILD`：prompt 构建后，可修改最终结果
     - `ON_SECTION_RENDER`：每个 section 渲染时，可动态修改内容

4. **SystemPromptPort 升级**：
   - 从 `build() -> str` 升级为 `build(pipeline: PromptPipeline) -> str`
   - Adapter 层负责注册默认 sections，用户可通过 Hook 追加

---

### Task 3: 工具调用 Hook 扩展

**目标**：在工具调用的完整生命周期中预留扩展点，支持审批、拦截、转换、监控。

**设计方案**：

新增 HookPoint：
```python
# 工具选择阶段（LLM 返回工具调用决定后，执行前）
BEFORE_TOOL_SELECTION    # 可修改/过滤 LLM 选择的工具列表
ON_TOOL_APPROVAL         # 高危工具审批（可阻断执行）

# 工具执行阶段（已有，增强）
BEFORE_TOOL_EXEC         # (已有) 增强：支持参数修改
AFTER_TOOL_EXEC          # (已有) 增强：支持结果转换/增强

# 工具注册阶段
ON_TOOL_REGISTER         # 工具注册时（可动态修改工具定义）
ON_TOOL_UNREGISTER       # 工具注销时

# 批量工具调用
ON_TOOL_BATCH_START      # 批量工具调用开始
ON_TOOL_BATCH_END        # 批量工具调用结束（可汇总结果）
```

**ToolMiddleware 管道**：
- 位置：`backend/src/agent_core/tool_middleware.py`
- 支持注册中间件链：`Cache → RateLimit → Approval → Retry → Timing → Executor`
- 每个中间件可决定 `proceed / abort / modify`

---

### Task 4: 定时任务稳定性 + Agent 粒度重构

**目标**：提升 Cron 系统稳定性，细化 Agent 执行粒度。

**稳定性改进**：

1. **APScheduler 版本策略**
   - 评估是否继续使用 4.0 alpha，或回退到稳定的 3.x
   - 添加调度器健康监控（心跳检测、任务积压告警）

2. **任务重试与容错**
   - 新增 `RetryPolicy`：`max_retries, backoff_strategy, dead_letter_queue`
   - 任务失败后自动重试，超过次数进入死信队列
   - 添加 `JobStatus` 状态机：`PENDING → RUNNING → SUCCESS/FAILED/RETRYING`

3. **内存管理**
   - `_job_history` 改用 LRU 缓存 + 最大条目限制
   - 历史记录持久化到 SQLite，内存只保留近期

4. **任务链支持**
   - 新增 `JobChain` 类型：定义 `Job A → Job B → Job C` 的依赖图
   - 支持条件分支：Job A 成功走 B，失败走 C

**Agent 粒度重构**：

```
当前：CronJob → 创建完整会话 → 完整 Agent 循环
改进：CronJob → 选择执行粒度 → 轻量/标准/完整模式
```

- **轻量模式 (light)**：直接调用 LLM，无工具/记忆，适用于简单通知
- **标准模式 (standard)**：当前行为，完整 Agent 循环
- **函数模式 (function)**：直接调用指定工具，跳过 LLM，适用于数据采集
- 在 JobConfig 中新增 `execution_mode: "light" | "standard" | "function"`

---

### Task 5: 多 Agent 协同运作设计

**目标**：建立多 Agent 协同的完整运作模式。

**协同模式设计**：

1. **主从模式 (Leader-Worker)**
   ```
   Main Agent (Leader)
     ├─ delegate("research", "查找相关资料") → Research Agent
     ├─ delegate("code", "实现功能") → Code Agent
     └─ aggregate results → 返回用户
   ```

2. **管道模式 (Pipeline)**
   ```
   User Input → Agent A (理解) → Agent B (规划) → Agent C (执行) → Output
   ```

3. **讨论模式 (Discussion)**
   ```
   Topic → Agent A (观点1) + Agent B (观点2) → Moderator Agent → 共识
   ```

**共享上下文设计**：

```python
class SharedContext:
    """多 Agent 共享的上下文空间"""
    context_id: str
    participants: list[str]  # 参与的 agent_ids
    shared_memory: dict      # 共享键值存储
    message_board: list      # 消息板（所有参与者可见）
    locks: dict              # 并发控制锁
```

位置：新建 `backend/src/agent_core/shared_context.py`

**Agent 能力发现**：

```python
class AgentCapability:
    agent_id: str
    capabilities: list[str]  # ["research", "code-analysis", "summarize"]
    load: float              # 当前负载 0.0-1.0
    status: str              # "idle" | "busy" | "offline"
```

Leader Agent 可通过 AgentRegistry 查询能力匹配的 Agent 进行委派。

---

## 五、实施优先级建议

| 优先级 | Task | 预估工作量 | 依赖 |
|--------|------|-----------|------|
| P0 | Task 2: Prompt Hook 扩展 | 3-5天 | 无，可独立实施 |
| P0 | Task 3: Tool 调用 Hook 扩展 | 2-3天 | 无，可独立实施 |
| P1 | Task 4: Cron 稳定性改进 | 3-5天 | 无，可独立实施 |
| P1 | Task 1: A2A 通信基础设施 | 5-8天 | 无，但建议先完成 P0 |
| P2 | Task 5: 多 Agent 协同 | 5-10天 | 依赖 Task 1 |
| P2 | Task 4: Agent 粒度重构 | 3-5天 | 依赖 Cron 稳定性 |

**建议实施路径**：
```
Phase 1 (1-2周): Prompt Hook + Tool Hook（扩展基础设施）
Phase 2 (2-3周): Cron 稳定性 + A2A 通信（核心能力）
Phase 3 (3-4周): 多 Agent 协同 + Agent 粒度（高级功能）
```

---

## 六、其他需同步加强的基础工作

1. **Conversation 模块解耦**：将 Identity 分离为独立模块，消除 `conversation ↔ gateway` 双向依赖
2. **错误处理统一**：定义 `ErrorType` 枚举和统一的 `Result[T]` 类型
3. **测试覆盖补齐**：优先为 Gateway Dispatcher 和 Agent Core 添加单元测试
4. **API 规范文档**：基于 Pydantic models 自动生成 OpenAPI spec + TypeScript types
