# Gateway + 通知系统 执行计划（v2）

> 基于 `gateway-tech.md` + `agent-notify-tech.md` 的最新技术方案重新拆解。
> Phase 1 (Task 1-3) 已完成，从 Phase 2 开始。

---

## 进度状态

| Phase | 状态 |
|-------|------|
| Phase 1: Gateway 核心层 | ✅ 已完成 |
| Phase 2: 系统集成 | 🔄 进行中 |
| Phase 3: 通知基础设施 | ⏳ 待开始 |
| Phase 4: Agent 主动触发 | ⏳ 待开始 |
| Phase 5: Channel 预留 + CLI | ⏳ 待开始 |

---

## ✅ Phase 1: Gateway 核心层（已完成）

| Task | 内容 | 状态 |
|------|------|------|
| 1 | 创建 Gateway 核心类型定义（Envelope、EnvelopeIntent、GatewayEvent、GatewayEventType、AgentInfo） | ✅ |
| 2 | 实现 AgentBridge，从 websocket.py 提取 Agent 编排逻辑 | ✅ |
| 3 | 实现 GatewayDispatcher（Agent 解析、Identity 构建、Session 管理、请求分发） | ✅ |

---

## 🔄 Phase 2: 系统集成（串行，Task 4→5）

**目标**：将 websocket.py 瘦身为纯协议层，新增 SSE 端点，所有业务逻辑下沉到 Gateway。

| Task | 内容 | 复杂度 | 依赖 | 状态 |
|------|------|--------|------|------|
| 4 | 重构 websocket.py 为纯协议层 | 🟡 Medium | Task 2, 3 | 🔄 进行中 |
| 5 | 新增 Gateway REST/SSE 端点 + 注册到 main.py | 🟡 Medium | Task 3, 4 | ⏳ |

### Task 4 详细拆解

**目标**：websocket.py 只保留 3 个职责：协议处理、Envelope 封装、GatewayEvent→WS JSON 转换。

**从 websocket.py 移除的逻辑（下沉到 Gateway）：**
- `create_agent_config()` → 移到 `AgentBridge.create_config()`
- `_get_tool_manager()` / `_get_llm_router()` / `_get_skill_adapter()` → 移到 `AgentBridge`
- `_handle_message()` 中的业务逻辑 → 移到 `GatewayDispatcher.dispatch()`
- `_persist_assistant_message()` → 移到 `GatewayDispatcher`
- `_load_session_history()` → 移到 `GatewayDispatcher`
- `_match_and_load_skill_prompt()` → 移到 `GatewayDispatcher`
- ChatSession 创建/管理 → 移到 `GatewayDispatcher`
- Identity/AgentContext 构建 → 移到 `GatewayDispatcher`

**websocket.py 重构后的结构：**
```python
# 纯协议层，约 100-150 行
@router.websocket("/agent/{session_id}")
async def agent_websocket(websocket, session_id):
    await websocket.accept()
    registry.register(session_id, ws_handle)  # 注册连接
    
    try:
        async for data in receive_messages():
            envelope = _ws_message_to_envelope(data, session_id)
            async for event in dispatcher.dispatch(envelope):
                ws_msg = _gateway_event_to_ws(event)
                if ws_msg:
                    await websocket.send_json(ws_msg)
    finally:
        registry.unregister(session_id, channel_id)  # 注销连接
```

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/gateway/agent_bridge.py` | 新建：从 websocket.py 提取 Agent 编排逻辑 |
| `backend/src/gateway/dispatcher.py` | 新建：请求分发、Session 管理、技能调度 |
| `backend/src/agent_core/api/websocket.py` | 重构：瘦身为纯协议层 |
| `backend/src/agent_core/api/converters.py` | 调整：支持 GatewayEvent 转换 |

### Task 5 详细拆解

**目标**：新增 `/api/v1/gateway/chat` SSE 端点，与 WebSocket 共享 Gateway 层。

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/api/v1/gateway.py` | 新建：SSE 端点 |
| `backend/src/main.py` | 修改：注册 gateway 路由 |

---

## 🆕 Phase 3: 通知基础设施（串行，Task 6→7→8）

**目标**：建立连接注册表、消息总线和通知路由器，为 Agent 主动推送奠定基础。

| Task | 内容 | 复杂度 | 依赖 | 状态 |
|------|------|--------|------|------|
| 6 | 实现 ConnectionRegistry（连接注册表） | 🟡 Medium | Task 4 | ⏳ |
| 7 | 实现 MessageBus + Outbox（消息总线 + 离线暂存） | 🟡 Medium | Task 6 | ⏳ |
| 8 | 实现 NotificationChannel 抽象 + NotificationRouter + WebChatChannel | 🟡 Medium | Task 6, 7 | ⏳ |

### Task 6 详细拆解

**目标**：全局单例连接注册表，管理所有活跃的 WS/SSE 连接。

**核心类：**
- `ConnectionRegistry` — 单例，`session_id → {channel_id → ConnectionHandle}` 映射
- `ConnectionHandle` — 连接句柄，包含 `send` 闭包
- `PushResult` — 推送结果

**集成点：**
- websocket.py 连接建立时 `register()`，断开时 `unregister()`
- SSE 端点连接建立时 `register()`，断开时 `unregister()`

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/gateway/connection_registry.py` | 新建 |
| `backend/src/agent_core/api/websocket.py` | 修改：接入 registry |
| `backend/src/api/v1/gateway.py` | 修改：SSE 接入 registry |

### Task 7 详细拆解

**目标**：消息总线，统一管理在线推送和离线暂存。

**核心类：**
- `MessageBus` — 在线推送 + 离线暂存
- `OutboundMessage` — 出站消息数据模型
- `ActiveSessionResolver` — Session 解析器（单聊单 session 规则）

**Outbox 存储**：复用现有 SQLite 存储，新增 `outbox_messages` 表。

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/gateway/message_bus.py` | 新建 |
| `backend/src/gateway/session_resolver.py` | 新建 |
| `backend/src/api/v1/gateway.py` | 修改：新增 `GET /outbox` 端点（重连拉取） |

### Task 8 详细拆解

**目标**：通知通道抽象和路由器，支持有状态（WebChat）和无状态（Telegram/DingTalk）通道。

**核心类：**
- `NotificationChannel` — Protocol 接口
- `NotificationTarget` — 通知目标
- `NotificationMessage` — 通知消息体
- `NotificationRouter` — 多通道路由器
- `WebChatNotificationChannel` — WebChat 通道实现（通过 ConnectionRegistry + MessageBus）

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/gateway/notification.py` | 新建 |

---

## 🆕 Phase 4: Agent 主动触发（串行，Task 9→10）

**目标**：让 Agent 具备主动推送和自动触发对话的能力。

| Task | 内容 | 复杂度 | 依赖 | 状态 |
|------|------|--------|------|------|
| 9 | 实现 AgentInvoker（Agent 自动触发器） | 🔴 High | Task 6, 7, 8 | ⏳ |
| 10 | 实现 NotifyTool（Agent 推送工具） | 🟡 Medium | Task 8 | ⏳ |

### Task 9 详细拆解

**目标**：非用户发起的 Agent 对话统一入口，完整 agent_loop 链路。

**核心类：**
- `AgentInvoker` — 自动触发器
- `InvokeSource` — 触发来源枚举（cron/webhook/agent/system）
- `InvokeResult` — 触发结果

**完整链路：**
1. Session 解析（ActiveSessionResolver）
2. 构建 Identity（ChannelProtocol.INTERNAL）
3. 设置 AgentContext + contextvars
4. 确保 ChatSession 存在
5. 创建 Agent + 加载历史
6. 执行 agent_loop
7. 持久化消息
8. 推送到 ConnectionRegistry / 暂存到 Outbox

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/gateway/agent_invoker.py` | 新建 |
| `backend/src/conversation/identity.py` | 修改：新增 `ChannelProtocol.INTERNAL` |
| `backend/src/conversation/context.py` | 修改：新增 `AgentContext.for_internal()` |

### Task 10 详细拆解

**目标**：Agent 的推送工具，支持多通道通知。

**核心类：**
- `NotifyTool` — BaseTool 实现

**工具参数：**
- `message` (必填): 通知内容
- `title` (可选): 通知标题
- `channels` (可选): 通知通道列表
- `urgency` (可选): 紧急程度

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/tools/builtin/notify_tool.py` | 新建 |
| `backend/src/agent_core/api/websocket.py` | 修改：注册 NotifyTool |

---

## 📦 Phase 5: Channel 预留 + CLI 基础（可并行）

**目标**：预留 Channel 扩展接口，搭建 CLI 基础结构。

| Task | 内容 | 复杂度 | 依赖 | 状态 | 并行组 |
|------|------|--------|------|------|--------|
| 11 | 创建 Channel 预留模块（ChannelAdapter 抽象基类 + ChannelRegistry） | 🟢 Low | Task 1 | ⏳ | A |
| 12 | 创建 CLI 独立包基础结构 | 🟢 Low | 无 | ⏳ | A |
| 13 | 实现 CLI 适配器（GatewayClient + OutputRenderer） | 🟡 Medium | Task 5, 12 | ⏳ | B |
| 14 | 实现 CLI chat 命令 | 🟡 Medium | Task 12, 13 | ⏳ | — |
| 15 | 实现 CLI 管理命令 | 🟡 Medium | Task 12, 13 | ⏳ | — |

**涉及文件：**
| 文件 | 操作 |
|------|------|
| `backend/src/channel/base.py` | 新建：ChannelAdapter 抽象基类 |
| `cli/pyproject.toml` | 新建 |
| `cli/src/main.py` | 新建 |
| `cli/src/gateway_client.py` | 新建 |
| `cli/src/output_renderer.py` | 新建 |
| `cli/src/commands/chat.py` | 新建 |
| `cli/src/commands/manage.py` | 新建 |

---

## 执行顺序图

```
Phase 1 (已完成)              Phase 2 (进行中)
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│ Task 1 │→ │ Task 2 │→ │ Task 3 │→ │ Task 4 │→ │ Task 5 │
│ 类型 ✅│  │Bridge✅│  │Disp. ✅│  │WS重构🔄│  │SSE端点 │
└────────┘  └────────┘  └────────┘  └────────┘  └────────┘
                                                      │
                                    Phase 3 (通知基础) │
                                    ┌────────┐         │
                                    │ Task 6 │◀────────┘
                                    │Registry│
                                    └───┬────┘
                                        │
                                    ┌───┴────┐
                                    │ Task 7 │
                                    │MsgBus  │
                                    └───┬────┘
                                        │
                                    ┌───┴────┐
                                    │ Task 8 │
                                    │Notify  │
                                    │Channel │
                                    └───┬────┘
                                        │
                         Phase 4 (Agent主动触发)
                         ┌────────┐     │
                         │ Task 9 │◀────┘
                         │Invoker │
                         └───┬────┘
                             │
                         ┌───┴────┐
                         │Task 10 │
                         │Notify  │
                         │Tool    │
                         └────────┘

Phase 5 (可与 Phase 3/4 并行)
┌────────┐  ┌────────┐
│Task 11 │  │Task 12 │
│Channel │  │CLI基础 │
└────────┘  └───┬────┘
                │
            ┌───┴────┐
            │Task 13 │
            │CLI适配 │
            └───┬────┘
                │
        ┌───────┼───────┐
        ▼               ▼
    ┌────────┐     ┌────────┐
    │Task 14 │     │Task 15 │
    │CLI chat│     │CLI管理 │
    └────────┘     └────────┘
```

---

## 关键路径

**主线**：Task 4 → 5 → 6 → 7 → 8 → 9 → 10

**并行线**：Task 11 + 12 可与 Phase 2/3 并行，Task 13-15 依赖 Task 5 + 12

---

## 资源映射

| 新模块 | Task | 依赖的现有模块 |
|--------|------|---------------|
| `backend/src/gateway/__init__.py` | Task 4 | — |
| `backend/src/gateway/envelope.py` | Task 1 ✅ | `conversation/identity.py` |
| `backend/src/gateway/response.py` | Task 1 ✅ | — |
| `backend/src/gateway/errors.py` | Task 1 ✅ | — |
| `backend/src/gateway/agent_bridge.py` | Task 4 | `agent_core/api/websocket.py`, `agent_core/config.py` |
| `backend/src/gateway/dispatcher.py` | Task 4 | `conversation/dao/`, `conversation/context.py`, `conversation/session.py` |
| `backend/src/gateway/connection_registry.py` | Task 6 | — |
| `backend/src/gateway/session_resolver.py` | Task 7 | `conversation/dao/` |
| `backend/src/gateway/message_bus.py` | Task 7 | `connection_registry.py`, `session_resolver.py` |
| `backend/src/gateway/notification.py` | Task 8 | `connection_registry.py`, `message_bus.py` |
| `backend/src/gateway/agent_invoker.py` | Task 9 | `dispatcher.py`, `agent_bridge.py`, `session_resolver.py` |
| `backend/src/api/v1/gateway.py` | Task 5 | `gateway/dispatcher.py` |
| `backend/src/tools/builtin/notify_tool.py` | Task 10 | `gateway/notification.py` |
| `agent_core/api/websocket.py` | Task 4 | `gateway/dispatcher.py`（重构后依赖） |
| `backend/src/main.py` | Task 5 | 路由注册 |
| `backend/src/channel/base.py` | Task 11 | `gateway/envelope.py`, `gateway/response.py` |
| `cli/` | Task 12-15 | `typer`, `rich`, `httpx` |