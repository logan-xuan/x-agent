# Agent 主动通知系统设计方案

> 本文档描述 X-Agent 的主动通知架构设计，使 Agent 具备跨渠道主动推送消息的能力。

---

## 一、背景与动机

当前 X-Agent 的消息流是**单向被动**的：用户发消息 → Agent 响应。但 Agent 作为个人助手，需要具备**主动触达**用户的能力：

- **定时提醒**：每日总结、待办提醒、天气播报
- **任务完成通知**：长时间运行的工具执行完毕后通知用户
- **事件驱动**：外部 Webhook 触发 Agent 思考并推送结果
- **多 Agent 协作**：一个 Agent 的结果需要通知到另一个 Agent 的用户

现有架构缺少三个关键能力：
1. **连接注册表**：不知道用户当前在哪个连接上
2. **反向推送通道**：无法从服务端主动向客户端发消息
3. **跨渠道通知**：无法向 Telegram/DingTalk 等 IM 平台推送

---

## 二、通知通道分类

### 2.1 有状态通道 vs 无状态通道

| 维度 | 有状态通道 (Stateful) | 无状态通道 (Stateless) |
|------|----------------------|----------------------|
| **代表** | WebSocket, SSE, CLI | Telegram, DingTalk, Slack, Email |
| **连接模型** | 需要活跃连接才能推送 | 通过平台 API 直接推送 |
| **Session** | 有 session 概念 | 无 session，用 chat_id / webhook |
| **离线处理** | 需要 Outbox 暂存 | 平台自带离线推送能力 |
| **用户在线** | 必须在线 | 不需要在线 |

### 2.2 各通道特征

| 通道 | 类型 | 需要 session? | 推送方式 | 离线处理 |
|------|------|--------------|---------|---------|
| **WebChat (WS)** | 有状态 | ✅ 自动解析/创建 | ConnectionRegistry | Outbox 暂存 |
| **WebChat (SSE)** | 有状态 | ✅ 自动解析/创建 | ConnectionRegistry | Outbox 暂存 |
| **CLI** | 有状态 | ✅ | stdout | 不支持 |
| **Telegram** | 无状态 | ❌ 用 chat_id | Bot API | 平台自带 |
| **DingTalk** | 无状态 | ❌ 用 webhook/user_id | Webhook/API | 平台自带 |
| **Slack** | 无状态 | ❌ 用 webhook | Webhook API | 平台自带 |
| **Email** | 无状态 | ❌ 用 email_address | SMTP/API | 天然异步 |

---

## 三、核心架构

### 3.1 架构全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  触发源                                                              │
│  ┌──────┐  ┌──────────┐  ┌──────────┐                               │
│  │ Cron │  │ Agent    │  │ Webhook  │                               │
│  │      │  │ (Tool)   │  │ (外部)   │                               │
│  └──┬───┘  └────┬─────┘  └────┬─────┘                               │
│     │           │             │                                     │
│     └───────────┼─────────────┘                                     │
│                 ▼                                                   │
│  ┌──────────────────────────────────────┐                           │
│  │  AgentInvoker (需要 Agent 思考)       │                           │
│  │  或                                  │                           │
│  │  NotificationRouter (直接通知)        │                           │
│  └──────────────┬───────────────────────┘                           │
│                 │                                                   │
│     ┌───────────┼───────────────────────────┐                       │
│     ▼           ▼           ▼               ▼                       │
│  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────────┐                 │
│  │WebChat │ │  CLI   │ │Telegram  │ │ DingTalk   │                 │
│  │Channel │ │Channel │ │Channel   │ │ Channel    │                 │
│  ├────────┤ ├────────┤ ├──────────┤ ├────────────┤                 │
│  │有状态   │ │有状态   │ │无状态     │ │无状态       │                 │
│  │Registry│ │stdout  │ │Bot API   │ │Webhook/API │                 │
│  │+Outbox │ │        │ │直接推送   │ │直接推送     │                 │
│  └────────┘ └────────┘ └──────────┘ └────────────┘                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
backend/src/gateway/
├── __init__.py
├── envelope.py              # 统一信封（已有设计）
├── dispatcher.py            # 请求分发（已有设计）
├── agent_bridge.py          # Agent Core 桥接（已有设计）
├── agent_invoker.py         # 🆕 Agent 自动触发器
├── connection_registry.py   # 🆕 连接注册表
├── notification.py          # 🆕 通知通道抽象 + 路由器
├── message_bus.py           # 🆕 消息总线（在线推送+离线暂存）
├── response.py              # 响应事件（已有设计）
└── errors.py
```

---

## 四、连接注册表（ConnectionRegistry）

### 4.1 设计

全局单例，管理所有活跃的客户端连接。各协议端点在连接建立时注册，断开时注销。

```python
class ConnectionRegistry:
    """全局连接注册表。

    管理所有活跃的客户端连接，支持按 session_id 查找和推送。
    每个 session_id 可以有多个连接（如同一会话的 WS + SSE）。
    """

    _instance: ConnectionRegistry | None = None

    def __init__(self):
        # session_id -> {channel_id -> ConnectionHandle}
        self._connections: dict[str, dict[str, ConnectionHandle]] = {}

    def register(self, session_id: str, handle: ConnectionHandle) -> None:
        """注册连接（WS connect / SSE subscribe 时调用）。"""

    def unregister(self, session_id: str, channel_id: str) -> None:
        """注销连接（disconnect 时调用）。"""

    def get_handles(self, session_id: str) -> list[ConnectionHandle]:
        """获取某 session 的所有活跃连接。"""

    async def push(self, session_id: str, message: dict) -> PushResult:
        """向指定 session 推送消息，自动选择可用连接。"""
```

### 4.2 ConnectionHandle

```python
@dataclass
class ConnectionHandle:
    """连接句柄 — 协议无关的消息发送抽象。

    send 是一个闭包，由各协议端点在连接建立时注入，
    屏蔽了 WebSocket/SSE/CLI 的协议差异。
    """
    channel_id: str
    channel_type: ChannelType
    channel_protocol: ChannelProtocol
    send: Callable[[dict], Awaitable[bool]]
    created_at: datetime
```

### 4.3 各端点的注册方式

**WebSocket 端点：**

```python
# websocket.py — 连接建立时
async def ws_sender(message: dict) -> bool:
    try:
        await websocket.send_json(message)
        return True
    except Exception:
        return False

registry.register(session_id, ConnectionHandle(
    channel_id=f"ws-{uuid4().hex[:8]}",
    channel_type=ChannelType.WEB_CHAT,
    channel_protocol=ChannelProtocol.WEBSOCKET,
    send=ws_sender,
    created_at=datetime.utcnow(),
))

# 断开时
registry.unregister(session_id, channel_id)
```

**SSE 端点：**

```python
# gateway.py — SSE 订阅时
sse_queue: asyncio.Queue[dict] = asyncio.Queue()

async def sse_sender(message: dict) -> bool:
    await sse_queue.put(message)
    return True

registry.register(session_id, ConnectionHandle(
    channel_id=f"sse-{uuid4().hex[:8]}",
    channel_type=ChannelType.WEB_CHAT,
    channel_protocol=ChannelProtocol.SSE,
    send=sse_sender,
    created_at=datetime.utcnow(),
))
```

---

## 五、Session 解析（ActiveSessionResolver）

### 5.1 核心规则

- **单聊单 session**：一个 agent_id 在一个渠道中，同时只有一个最新的 session_id 有效
- **自动创建**：通知时如果没有有效 session，自动创建新 session
- **Session 失效**：用户关闭窗口 → 旧 session 标记为 closed

### 5.2 设计

```python
class ActiveSessionResolver:
    """解析 Agent 在指定渠道的最新有效 Session。

    核心逻辑：
    1. 查找 agent_id + channel_type 下 status=ACTIVE 的最新 session
    2. 找到 → 返回该 session_id
    3. 没找到 → 自动创建新 session 并返回
    """

    async def resolve(
        self,
        agent_id: str,
        channel_type: ChannelType,
        auto_create: bool = True,
    ) -> str:
        """解析最新有效的 session_id。

        Args:
            agent_id: Agent ID
            channel_type: 渠道类型
            auto_create: 没有有效 session 时是否自动创建

        Returns:
            session_id

        Raises:
            NoActiveSessionError: auto_create=False 且无有效 session
        """
        # 1. 查找最新的 ACTIVE session
        session = await self._dao.get_latest_active(
            agent_id=agent_id,
            channel_type=channel_type,
        )

        if session:
            return session.id

        # 2. 没有有效 session → 自动创建
        if auto_create:
            new_session_id = str(uuid4())
            await self._dao.create(
                session_id=new_session_id,
                agent_id=agent_id,
                channel_type=channel_type,
                user_id=DEFAULT_USER_ID,
                channel_id=DEFAULT_CHANNEL_ID,
            )
            return new_session_id

        raise NoActiveSessionError(
            f"No active session for agent={agent_id}, channel={channel_type}"
        )
```

---

## 六、通知通道抽象（NotificationChannel）

### 6.1 统一接口

```python
class NotificationChannel(Protocol):
    """通知通道抽象 — 有状态和无状态通道的统一接口。"""

    @property
    def channel_type(self) -> ChannelType: ...

    @property
    def is_stateful(self) -> bool:
        """是否是有状态通道（需要活跃连接）。"""
        ...

    async def send(
        self,
        target: NotificationTarget,
        message: NotificationMessage,
    ) -> SendResult:
        """发送通知。"""
        ...

    async def is_available(self, target: NotificationTarget) -> bool:
        """检查目标是否可达。"""
        ...
```

### 6.2 通知目标

```python
@dataclass
class NotificationTarget:
    """通知目标 — 协议无关的目标标识。

    不同通道使用不同的字段：
    - WebChat: session_id（或 agent_id + channel_type 自动解析）
    - Telegram: chat_id
    - DingTalk: webhook_url 或 user_id
    - Email: email_address
    """
    agent_id: str | None = None
    session_id: str | None = None
    chat_id: str | None = None
    webhook_url: str | None = None
    user_id: str | None = None
    email_address: str | None = None
```

### 6.3 通知消息

```python
@dataclass
class NotificationMessage:
    """通知消息体。"""
    content: str
    title: str | None = None
    urgency: str = "normal"             # low / normal / high
    source: str = "agent"               # agent / cron / system
    message_type: str = "notification"  # notification / reminder / alert / conversation
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### 6.4 有状态通道实现（WebChat）

```python
class WebChatNotificationChannel:
    """WebChat 通知通道 — 通过 ConnectionRegistry 推送。"""

    channel_type = ChannelType.WEB_CHAT
    is_stateful = True

    async def send(self, target, message) -> SendResult:
        registry = get_connection_registry()

        # 解析 session_id
        session_id = target.session_id
        if not session_id:
            resolver = ActiveSessionResolver()
            session_id = await resolver.resolve(
                agent_id=target.agent_id or DEFAULT_AGENT_ID,
                channel_type=ChannelType.WEB_CHAT,
                auto_create=True,
            )

        # 尝试实时推送
        handles = registry.get_handles(session_id)
        if handles:
            for handle in handles:
                success = await handle.send(message.to_ws_dict())
                if success:
                    return SendResult(delivered=True, session_id=session_id)

        # 离线 → outbox 暂存
        await self._save_to_outbox(session_id, message)
        return SendResult(delivered=False, queued=True, session_id=session_id)
```

### 6.5 无状态通道实现（Telegram）

```python
class TelegramNotificationChannel:
    """Telegram 通知通道 — 通过 Bot API 直接推送。"""

    channel_type = ChannelType.TELEGRAM
    is_stateful = False

    async def send(self, target, message) -> SendResult:
        chat_id = target.chat_id or self._config.default_chat_id
        if not chat_id:
            return SendResult(delivered=False, error="No chat_id configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": self._format_message(message),
                    "parse_mode": "Markdown",
                },
            )

        return SendResult(delivered=response.is_success)
```

### 6.6 无状态通道实现（DingTalk）

```python
class DingTalkNotificationChannel:
    """DingTalk 通知通道 — 通过 Webhook 或 API 推送。"""

    channel_type = ChannelType.DINGTALK
    is_stateful = False

    async def send(self, target, message) -> SendResult:
        webhook_url = target.webhook_url or self._config.default_webhook
        if not webhook_url:
            return SendResult(delivered=False, error="No webhook configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json={
                    "msgtype": "markdown",
                    "markdown": {
                        "title": message.title or "X-Agent 通知",
                        "text": message.content,
                    },
                },
            )

        return SendResult(delivered=response.is_success)
```

---

## 七、通知路由器（NotificationRouter）

```python
class NotificationRouter:
    """通知路由器 — 根据目标自动选择通知通道。

    支持多通道同时通知（如 WebChat + DingTalk 同时推送）。
    """

    def __init__(self):
        self._channels: dict[ChannelType, NotificationChannel] = {}

    def register(self, channel: NotificationChannel) -> None:
        """注册通知通道。"""
        self._channels[channel.channel_type] = channel

    async def notify(
        self,
        message: NotificationMessage,
        *,
        targets: list[NotificationTarget] | None = None,
        channel_types: list[ChannelType] | None = None,
        broadcast: bool = False,
    ) -> list[SendResult]:
        """发送通知。

        路由策略：
        1. 指定 targets → 按 target 中的信息路由到对应通道
        2. 指定 channel_types → 向指定类型的所有已注册通道发送
        3. broadcast=True → 向所有已注册通道广播
        4. 都没指定 → 使用默认通道（WebChat）
        """
```

---

## 八、Agent 自动触发器（AgentInvoker）

### 8.1 设计动机

当 Cron 定时任务或外部事件需要触发 Agent 对话时，不是简单推送文本，
而是需要经过完整的 `agent_core loop` 流程——加载身份上下文、会话历史、技能、工具等。

### 8.2 与 NotifyTool 的关系

| 工具 | 触发方 | 经过 agent_loop? | 适用场景 |
|------|--------|-----------------|---------|
| **NotifyTool** | Agent 自己（在对话中） | ❌ 直接推送文本 | 简单通知、进度更新 |
| **AgentInvoker** | Cron / Webhook / 系统 | ✅ 完整 loop | 需要 Agent 思考的场景 |

### 8.3 完整链路

```
Cron Trigger / External Event
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  AgentInvoker.invoke(content, channel_type=...)      │
│                                                     │
│  1. Session 解析                                     │
│     session_id 传入 → 直接使用                        │
│     session_id 未传入 → ActiveSessionResolver 解析    │
│     无有效 session → 自动创建                         │
│                                                     │
│  2. 构建 Identity                                    │
│     Identity(                                       │
│       session_id = resolved_session_id,             │
│       trace_id   = uuid4(),                         │
│       agent_id   = agent_id or DEFAULT,             │
│       channel_type = channel_type,                  │
│       channel_protocol = INTERNAL,  ← 标记内部触发   │
│       user_id    = "system",                        │
│     )                                               │
│                                                     │
│  3. 设置 AgentContext + contextvars                   │
│     ctx = AgentContext.for_internal(...)             │
│     set_current_context(ctx)                        │
│     ↑ 确保 agent_loop 内部 get_current_context() 正常 │
│                                                     │
│  4. 确保 ChatSession 存在                             │
│     ChatSessionDAO.get_or_create(session_id)        │
│                                                     │
│  5. 创建 Agent + 加载历史                             │
│     config = create_agent_config()                  │
│     agent = Agent(config)                           │
│     _load_session_history(agent, session_id)        │
│                                                     │
│  6. 执行 agent_loop                                  │
│     async for event in agent.run(content):          │
│       → 收集 AgentEvent 流                           │
│       → 实时推送到 ConnectionRegistry（如果在线）      │
│                                                     │
│  7. 持久化                                           │
│     SessionManager.add_message(role="system")       │
│     SessionManager.add_message(role="assistant")    │
│                                                     │
│  8. 离线兜底                                         │
│     推送失败 → MessageBus.save_to_outbox()           │
└─────────────────────────────────────────────────────┘
```

### 8.4 接口设计

```python
class InvokeSource(str, Enum):
    """触发来源。"""
    CRON = "cron"
    WEBHOOK = "webhook"
    AGENT = "agent"       # Agent-to-Agent
    SYSTEM = "system"

@dataclass
class InvokeResult:
    """触发结果。"""
    session_id: str
    trace_id: str
    delivered: bool           # 是否实时推送成功
    queued: bool = False      # 是否暂存到 outbox
    response: str | None = None  # Agent 的回复内容

class AgentInvoker:
    """Agent 自动触发器 — 非用户发起的 Agent 对话统一入口。

    使用场景：
    1. Cron 定时任务触发 Agent 思考并推送结果
    2. 外部事件（webhook）触发 Agent 响应
    3. Agent 工具中触发另一个 Agent 对话（多 Agent 协作）
    4. 系统级通知需要 Agent 润色后推送
    """

    async def invoke(
        self,
        content: str,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        source: InvokeSource = InvokeSource.CRON,
        metadata: dict | None = None,
    ) -> InvokeResult:
        """触发一次完整的 Agent 对话。

        Args:
            content: 触发消息内容（作为 system/user prompt 传入 agent_loop）
            session_id: 目标会话 ID（可选，未传入时自动解析）
            agent_id: 目标 Agent ID（可选，默认 DEFAULT_AGENT_ID）
            channel_type: 目标渠道类型
            source: 触发来源
            metadata: 附加元数据
        """
```

### 8.5 ChannelProtocol 扩展

```python
class ChannelProtocol(str, Enum):
    """渠道底层通信协议。"""
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    SSE = "sse"
    INTERNAL = "internal"    # 🆕 内部触发（cron/webhook/agent-to-agent）
```

### 8.6 AgentContext.for_internal() 工厂方法

```python
@classmethod
def for_internal(
    cls,
    session_id: str,
    *,
    source: str = "cron",
    agent_id: str | None = None,
    channel_type: ChannelType = ChannelType.WEB_CHAT,
    **metadata: Any,
) -> "AgentContext":
    """为内部触发（cron/webhook）创建上下文。

    与 for_websocket 的区别：
    - channel_protocol = INTERNAL
    - user_id = "system"
    - metadata 中携带 source 信息
    """
    identity_mgr = get_identity_manager()
    identity = identity_mgr.create(
        session_id=session_id,
        agent_id=agent_id,
        channel_type=channel_type,
        channel_protocol=ChannelProtocol.INTERNAL,
        user_id="system",
        metadata={"source": source, **metadata},
    )
    return cls(identity=identity, metadata={"source": source, **metadata})
```

---

## 九、Agent 工具：NotifyTool

### 9.1 设计

Agent 在对话过程中可以通过 NotifyTool 主动向用户推送消息，支持多通道。

```python
class NotifyTool(BaseTool):
    """向用户发送通知 — 支持多通道。"""

    name = "notify"
    description = """向用户发送通知消息。

参数:
- message: 通知内容（必填）
- title: 通知标题（可选）
- channels: 通知通道列表（可选，默认当前通道）
  可选值: web_chat, telegram, dingtalk, email
  支持多选如 ["web_chat", "dingtalk"] 同时通知
- urgency: 紧急程度 low/normal/high（可选，默认 normal）
"""

    parameters = {
        "message": {"type": "string", "description": "通知内容", "required": True},
        "title": {"type": "string", "description": "通知标题"},
        "channels": {
            "type": "array",
            "items": {"type": "string"},
            "description": "通知通道列表，不填则使用当前通道",
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "normal", "high"],
            "default": "normal",
        },
    }

    async def execute(self, message, title=None, channels=None, urgency="normal"):
        router = get_notification_router()

        notification = NotificationMessage(
            content=message,
            title=title,
            urgency=urgency,
            source="agent",
        )

        if channels:
            channel_types = [ChannelType(c) for c in channels]
            results = await router.notify(notification, channel_types=channel_types)
        else:
            results = await router.notify(notification)

        delivered = sum(1 for r in results if r.delivered)
        queued = sum(1 for r in results if r.queued)

        return f"✅ {delivered} 个通道已送达, 📬 {queued} 个通道已暂存"
```

---

## 十、消息总线（MessageBus）

### 10.1 设计

统一管理在线推送和离线暂存，是 ConnectionRegistry 和 Outbox 的上层封装。

```python
class MessageBus:
    """消息总线 — 在线推送 + 离线暂存。

    推送策略：
    1. 先尝试通过 ConnectionRegistry 实时推送
    2. 推送失败（用户离线）→ 写入 outbox 表
    3. 用户重连时 → 拉取并投递 outbox 中的未读消息
    """

    async def send(
        self,
        session_id: str,
        message: OutboundMessage,
        persist: bool = True,
    ) -> SendResult:
        """发送消息到指定 session。"""

    async def drain_outbox(self, session_id: str) -> list[OutboundMessage]:
        """用户重连时，拉取所有未投递的消息。"""
```

### 10.2 Outbox 数据模型

```python
@dataclass
class OutboundMessage:
    """出站消息。"""
    id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    title: str | None = None
    message_type: str = "notification"
    source: str = "agent"
    urgency: str = "normal"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    delivered: bool = False
    delivered_at: datetime | None = None
```

---

## 十一、消息流转全景

### 场景 1: 用户在线 — 实时推送

```
┌──────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│ Cron │───▶│AgentInvoker  │───▶│agent_loop()  │───▶│Registry  │──▶ WS 推送
│      │    │resolve session│    │完整对话流程   │    │找到连接   │
└──────┘    └──────────────┘    └──────────────┘    └──────────┘
```

### 场景 2: 用户离线（关闭了窗口）— Outbox 暂存

```
┌──────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐    ┌────────┐
│ Cron │───▶│AgentInvoker  │───▶│agent_loop()  │───▶│Registry  │───▶│Outbox  │
│      │    │auto-create   │    │完整对话流程   │    │无连接     │    │暂存消息│
└──────┘    │session       │    │              │    └──────────┘    └────────┘
            └──────────────┘    └──────────────┘
```

### 场景 3: 用户重新打开窗口 — 拉取未读

```
┌──────────┐    ┌──────────────┐    ┌────────┐
│ 前端     │───▶│ GET /outbox  │───▶│ Drain  │──▶ 投递暂存消息
│ 重连     │    │              │    │        │
└──────────┘    └──────────────┘    └────────┘
```

### 场景 4: IM 通道通知（Telegram/DingTalk）— 直接推送

```
┌──────┐    ┌──────────────┐    ┌──────────────┐
│ Cron │───▶│Notification  │───▶│Telegram API  │──▶ 直接送达
│      │    │Router        │    │DingTalk API  │    （平台处理离线）
└──────┘    └──────────────┘    └──────────────┘
```

---

## 十二、Cron 任务使用示例

### 12.1 简单通知（不需要 Agent 思考）

```python
# workspace/jobs/daily_reminder.py

async def daily_reminder_task():
    """每日提醒 — 直接推送文本"""
    from src.gateway.notification import get_notification_router, NotificationMessage

    router = get_notification_router()
    await router.notify(
        NotificationMessage(
            content="🌅 早安！今天也要加油哦~",
            title="每日问候",
            source="cron",
            urgency="low",
        ),
        channel_types=[ChannelType.WEB_CHAT, ChannelType.TELEGRAM],
    )
```

### 12.2 Agent 思考后推送（需要完整 loop）

```python
# workspace/jobs/daily_summary.py

async def daily_summary_task():
    """每日总结 — 让 Agent 回顾对话并生成总结"""
    from src.gateway.agent_invoker import get_agent_invoker

    invoker = get_agent_invoker()
    result = await invoker.invoke(
        content="请回顾我们今天的所有对话，生成一份简洁的每日总结。",
        channel_type=ChannelType.WEB_CHAT,
        source=InvokeSource.CRON,
        metadata={"task_name": "daily_summary"},
    )
    # result.delivered / result.response / result.trace_id
```

### 12.3 多通道同时通知

```python
# workspace/jobs/important_alert.py

async def important_alert_task():
    """重要告警 — 同时推送到 WebChat + DingTalk + Telegram"""
    from src.gateway.notification import get_notification_router, NotificationMessage

    router = get_notification_router()
    await router.notify(
        NotificationMessage(
            content="⚠️ 服务器 CPU 使用率超过 90%",
            title="系统告警",
            source="system",
            urgency="high",
        ),
        broadcast=True,  # 向所有已注册通道广播
    )
```

---

## 十三、与 Gateway 重构的关系

本设计是 Gateway 重构（`gateway-tech.md`）的自然延伸：

| Gateway 已有设计 | 通知系统新增 | 关系 |
|-----------------|------------|------|
| Envelope（统一信封） | NotificationMessage | 入站 vs 出站的消息抽象 |
| Dispatcher（请求分发） | AgentInvoker | 用户发起 vs 系统发起的 Agent 对话 |
| AgentBridge | — | AgentInvoker 复用 AgentBridge |
| GatewayEvent | — | AgentInvoker 的事件流复用 GatewayEvent |
| — | ConnectionRegistry | 新增：活跃连接管理 |
| — | NotificationRouter | 新增：多通道通知路由 |
| — | MessageBus | 新增：在线推送+离线暂存 |

**核心原则**：`AgentInvoker` 本质上就是一个不需要协议端点的 Dispatcher，
它直接构造 Envelope 并调用 AgentBridge，复用 Gateway 的全部基础设施。

---

## 十四、实施计划

| Phase | 内容 | 依赖 |
|-------|------|------|
| **Phase 2.5** | ConnectionRegistry + MessageBus | Phase 2 (WS 重构) |
| **Phase 2.5** | ActiveSessionResolver | ChatSessionDAO |
| **Phase 2.5** | NotificationRouter + WebChatChannel | ConnectionRegistry |
| **Phase 2.5** | AgentInvoker | AgentBridge + ActiveSessionResolver |
| **Phase 2.5** | NotifyTool | NotificationRouter |
| **Phase 3+** | TelegramChannel / DingTalkChannel | NotificationRouter |
| **Phase 3+** | 前端通知 UI（toast + 浏览器通知） | WebSocket 消息协议扩展 |
