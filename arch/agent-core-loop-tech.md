# Agent-Core 架构设计文档 V3

> 本文档描述 Agent Core 的 Port/Adapter 架构设计与扩展机制。

---

## 一、架构概览

Agent Core 采用 **六边形架构（Port/Adapter）**，实现核心逻辑与外部系统的解耦：

```
                    ┌─────────────────────────────────────┐
                    │           Agent Core                │
                    │  ┌─────────┐  ┌─────────┐          │
                    │  │ Agent   │  │ Loop    │          │
                    │  │         │  │ Runner  │          │
                    │  └────┬────┘  └────┬────┘          │
                    │       │            │                │
                    │  ┌────▼────────────▼────┐           │
                    │  │     Ports (Protocol) │           │
                    │  │  - LLMPort           │           │
                    │  │  - ToolPort          │           │
                    │  │  - MemoryPort        │           │
                    │  │  - LoggerPort        │           │
                    │  │  - PlanPort    🆕    │           │
                    │  │  - ContextPort 🆕    │           │
                    │  │  - SkillPort   🆕    │           │
                    │  └──────────┬───────────┘           │
                    └─────────────┼───────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
        │ LLM       │      │ Tool      │      │ Memory    │
        │ Adapter   │      │ Adapter   │      │ Adapter   │
        └───────────┘      └───────────┘      └───────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **Core 零依赖** | 核心模块仅使用 Python 标准库 |
| **Port 接口** | Protocol 定义接口，实现可替换 |
| **依赖注入** | 通过 AgentCoreConfig 注入适配器 |
| **Hook 扩展** | 生命周期节点可注入自定义逻辑 |
| **中间件链** | 管道式处理消息和工具调用 |

---

## 二、目录结构

```
agent_core/
├── ports/                   # Port 接口定义
│   ├── llm_port.py          # LLM 调用接口
│   ├── tool_port.py         # 工具执行接口
│   ├── memory_port.py       # 记忆存储接口
│   ├── plan_port.py         # 🆕 计划管理接口
│   ├── context_port.py      # 🆕 上下文管理接口
│   └── skill_port.py        # 🆕 技能系统接口
├── adapters/                # 适配器实现（连接外部系统）
├── hooks.py                 # 🆕 Hook 机制
├── middleware.py            # 🆕 中间件模式
├── registry.py              # 🆕 组件注册中心
├── config.py                # 配置与依赖注入
├── agent_loop.py            # Agent Loop 核心
└── api/                     # WebSocket/REST API
```

---

## 三、Port 接口规范

### 3.1 接口职责

| Port | 职责 | 核心方法 |
|------|------|----------|
| LLMPort | LLM 调用 | `stream()` |
| ToolPort | 工具执行 | `execute()`, `get_tools()` |
| MemoryPort | 记忆存储 | `store()`, `search()` |
| LoggerPort | 日志记录 | `log()`, `subscribe()` |
| PlanPort 🆕 | 计划管理 | `generate_plan()`, `update_step()`, `should_replan()` |
| ContextPort 🆕 | 上下文管理 | `compress()`, `estimate_tokens()` |
| SkillPort 🆕 | 技能系统 | `register()`, `discover()`, `execute()` |

### 3.2 接口约束

- **Protocol 类型**：使用 Python Protocol 实现结构化子类型
- **异步优先**：所有 I/O 操作使用 `async/await`
- **错误隔离**：适配器异常不应导致核心崩溃
- **可选实现**：除 LLMPort 外，其他 Port 均可选

---

## 四、扩展机制

### 4.1 Hook 生命周期链路

```
[用户输入]
    │
    ▼
ON_TURN_START
    │
    ▼
BEFORE_LLM_CALL ──► LLM 调用 ──► AFTER_LLM_CALL
    │                              │
    │        ┌─────────────────────┘
    │        ▼
    │   ON_CONTEXT_OVERFLOW (如果溢出)
    │        │
    │        ▼
    │   ON_CONTEXT_COMPRESS
    │        │
    ▼   ◄────┘
BEFORE_TOOL_EXEC ──► 工具执行 ──► AFTER_TOOL_EXEC
    │                              │
    │        ┌─────────────────────┘
    │        ▼
    │   ON_PLAN_GENERATED / ON_REPLAN
    │        │
    ▼   ◄────┘
ON_TURN_END
    │
    ▼
ON_ERROR (如果出错)
```

### 4.2 中间件链路

```
消息处理链:
Input ──► [Logging] ──► [Compression] ──► [Validation] ──► Handler ──► Output

工具执行链:
ToolCall ──► [Cache] ──► [Retry] ──► [Timing] ──► Executor ──► Result
```

### 4.3 扩展点对比

| 扩展点 | 适用场景 | 执行时机 |
|--------|----------|----------|
| **Port** | 接入外部系统 | 初始化时注入 |
| **Hook** | 生命周期事件处理 | 运行时触发 |
| **Middleware** | 数据管道处理 | 每次调用经过 |
| **Registry** | 组件动态管理 | 注册/发现时 |

---

## 五、配置注入规范

### 5.1 配置结构

```
AgentCoreConfig
├── 核心端口
│   ├── llm: LLMPort (必需)
│   ├── tools: ToolPort
│   ├── memory: MemoryPort
│   └── logger: LoggerPort
├── 扩展端口 🆕
│   ├── plan: PlanPort
│   ├── context: ContextPort
│   └── skill: SkillPort
├── 功能开关
│   ├── enable_plan: bool
│   ├── enable_context_compression: bool
│   └── enable_memory: bool
└── 扩展点 🆕
    ├── hooks: HookRegistry
    ├── message_middlewares: MiddlewareChain
    └── tool_middlewares: MiddlewareChain
```

### 5.2 链式配置

```python
config = AgentCoreConfig(llm=llm_adapter) \
    .with_tools(tool_adapter) \
    .with_plan(plan_adapter) \
    .with_hooks(hook_registry) \
    .add_tool_middleware(RetryMiddleware())
```

---

## 六、数据流总览

```
┌─────────────────────────────────────────────────────────────────┐
│                       Frontend (TypeScript)                      │
├─────────────────────────────────────────────────────────────────┤
│  ChatPage ──► useAgent hook ──► WebSocket ─────────────────┐    │
│  MessageList                                               │    │
│  DebugPanel ◄────── REST API (/api/v1/agent/logs)         │    │
└───────────────────────────────────────────────────────────│────┘
                                                            │
                        WebSocket                           │
                            │                               │
┌───────────────────────────▼───────────────────────────────┘────┐
│                       Backend (Python)                          │
├─────────────────────────────────────────────────────────────────┤
│  api/websocket.py ──► agent.py ──► agent_loop.py               │
│                                      │                          │
│                    ┌─────────────────┼─────────────────┐        │
│                    ▼                 ▼                 ▼        │
│               LLMPort          ToolPort         MemoryPort      │
│                    │                 │                 │        │
│                    └────────┬────────┴────────┬────────┘        │
│                             ▼                 ▼                 │
│                        hooks.py         middleware.py           │
│                             │                 │                 │
│                             └────────┬────────┘                 │
│                                      ▼                          │
│                               logger.py                         │
│                                      │                          │
│                                      ▼                          │
│                          api/routes.py (REST)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、日志记录点

| 触发点 | 事件名 | 记录内容 |
|--------|--------|----------|
| Agent 开始 | `agent_loop_start` | prompt 数量、model、tools |
| Agent 结束 | `agent_loop_end` | 总消息数、turn 数、耗时 |
| LLM 调用 | `llm_call_start/end` | model、tokens、usage、耗时 |
| 工具执行 | `tool_call_start/end` | tool_name、arguments、result |
| 上下文溢出 | `on_context_overflow` | 当前 tokens、限制 |
| 计划生成 | `plan_generated` | plan_id、steps |
| 重规划 | `replan` | 原因、新计划 |
| 错误 | `agent_loop_error` | 错误信息、堆栈 |

---

## 八、稳定性保障

| 机制 | 说明 |
|------|------|
| **接口隔离** | Port 接口最小化，单一职责 |
| **版本契约** | 接口版本化，向后兼容 |
| **依赖注入** | 核心不依赖具体实现 |
| **事件驱动** | 解耦组件通信 |
| **优雅降级** | 扩展失败不影响核心流程 |

**降级示例**：
```python
# 扩展端口可选，不存在时跳过
if config.plan:
    plan = await config.plan.generate_plan(goal, context)
# 无 plan 时走标准 ReAct 流程
```

---

## 九、实现路径

| 优先级 | 模块 | 说明 |
|--------|------|------|
| P0 | PlanAdapter | 计划管理，支持复杂任务 |
| P0 | ContextAdapter | 上下文压缩，解决长对话 |
| P1 | SkillAdapter | 集成现有技能系统 |
| P2 | 更多 Hook 点 | 按需求扩展 |
| P2 | 更多中间件 | 缓存、限流等 |

---

## 十、相关文件

| 文件 | 说明 |
|------|------|
| [ports/plan_port.py](../backend/src/agent_core/ports/plan_port.py) | 计划管理接口 |
| [ports/context_port.py](../backend/src/agent_core/ports/context_port.py) | 上下文管理接口 |
| [ports/skill_port.py](../backend/src/agent_core/ports/skill_port.py) | 技能系统接口 |
| [hooks.py](../backend/src/agent_core/hooks.py) | Hook 机制实现 |
| [middleware.py](../backend/src/agent_core/middleware.py) | 中间件实现 |
| [registry.py](../backend/src/agent_core/registry.py) | 组件注册中心 |
| [config.py](../backend/src/agent_core/config.py) | 配置与依赖注入 |
