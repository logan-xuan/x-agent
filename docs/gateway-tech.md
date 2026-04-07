# Gateway / Channel / CLI 系统重构设计方案

> 本文档描述 X-Agent 系统重构的架构设计，新增 Gateway 网关层、Channel 渠道层和 CLI 命令行端。

---

## 一、现状分析

当前系统的消息入口是 **WebSocket 端点**（`agent_core/api/websocket.py`），它直接耦合了以下职责：

1. **协议处理**：WebSocket 连接管理、心跳、消息解析
2. **业务编排**：创建 `AgentCoreConfig`、注入适配器、技能调度
3. **会话管理**：Session 创建/加载、上下文构建
4. **事件转换**：将 `AgentEvent` 转为 WebSocket JSON 消息

如果要新增 CLI 或钉钉等入口，必须**重复**上述 2-3 的逻辑。系统已有的 `Identity` 模型（`ChannelType`、`ChannelProtocol`）为多渠道做了预留，但缺少一个统一的消息入口层。

---

## 二、目标架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Endpoints (协议层)                           │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────────────┐    │
│  │ WebChat  │   │   CLI    │   │  Channel (预留)              │    │
│  │ (WS/REST)│   │ (stdin)  │   │  dingtalk / wechat / tg / .. │    │
│  └────┬─────┘   └────┬─────┘   └──────────────┬───────────────┘    │
│       │              │                         │                    │
│       └──────────────┼─────────────────────────┘                    │
│                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Gateway (网关层)                           │   │
│  │                                                              │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │   │
│  │  │ Envelope    │  │ Dispatcher   │  │ Response          │   │   │
│  │  │ (统一信封)   │  │ (请求分发)    │  │ Renderer (响应渲染)│   │   │
│  │  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘   │   │
│  │         │               │                    │              │   │
│  └─────────┼───────────────┼────────────────────┼──────────────┘   │
│            │               │                    │                   │
│            ▼               ▼                    ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Agent Core (核心层)                        │   │
│  │  agent_loop / ports / adapters / hooks / middleware          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Infrastructure (基础设施层)                      │   │
│  │  memory / config / storage / llm / tools / skills / cron     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **协议无关** | Gateway 只接收统一信封（Envelope），不关心消息来自 WS/CLI/HTTP |
| **单一入口** | 所有消息都经过 Gateway → Agent Core，消除重复编排逻辑 |
| **渠道独立** | 每个 Endpoint 是独立模块，只负责协议适配和信封封装 |
| **渐进式** | Channel 预留接口，不影响现有 WebChat 和新增 CLI 的开发 |
| **多 Agent** | Envelope 携带 agent_id/agent_name，支持多 Agent 路由 |

---

## 三、Gateway 设计

### 3.1 统一消息信封（Envelope）

Gateway 的核心抽象是 **Envelope**——一个协议无关的消息容器。

**目录结构：**

```
backend/src/gateway/
├── __init__.py
├── envelope.py          # 统一消息信封
├── dispatcher.py        # 请求分发器
├── response.py          # 响应事件定义
├── agent_bridge.py      # Agent Core 桥接器
└── errors.py            # Gateway 错误定义
```

**`envelope.py`** — 统一信封定义：

```python
@dataclass
class Envelope:
    """协议无关的统一消息信封。

    所有上游端点（WebChat / CLI / Channel）将各自协议的消息
    转换为 Envelope 后交给 Gateway 处理。

    Attributes:
        message_id:       消息唯一标识
        session_id:       会话标识（同一对话共享）
        content:          用户消息文本
        images:           附带的图片列表 [(base64, mime_type)]
        channel_type:     消息来源渠道
        channel_protocol: 底层通信协议
        user_id:          终端用户标识
        channel_id:       通道标识（如 WS 连接 ID）
        agent_id:         目标 Agent ID（None 时使用默认 Agent）
        agent_name:       目标 Agent 名称（可选，用于按名称路由）
        metadata:         渠道特有的附加数据
        intent:           消息意图（chat / abort / command）
    """
    message_id: str
    session_id: str
    content: str
    channel_type: ChannelType
    channel_protocol: ChannelProtocol

    # 可选字段
    images: list[tuple[str, str]] = field(default_factory=list)
    user_id: str | None = None
    channel_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    intent: EnvelopeIntent = EnvelopeIntent.CHAT

class EnvelopeIntent(str, Enum):
    """消息意图。"""
    CHAT = "chat"           # 普通对话
    ABORT = "abort"         # 中断当前处理
    COMMAND = "command"     # 系统命令（如 /config, /tools）
    PING = "ping"           # 心跳
```

**Agent 路由优先级**：`agent_id` > `agent_name` > 默认 Agent

### 3.2 请求分发器（Dispatcher）

**`dispatcher.py`** — 核心分发逻辑：

```python
class GatewayDispatcher:
    """Gateway 请求分发器。

    职责：
    1. 接收 Envelope
    2. 解析目标 Agent
    3. 构建 Identity + AgentContext
    4. 创建/恢复 Session
    5. 调用 AgentBridge 执行 agent_loop
    6. 返回 AsyncGenerator[GatewayEvent]
    """

    async def dispatch(self, envelope: Envelope) -> AsyncGenerator[GatewayEvent, None]:
        """分发消息到 Agent Core。"""

    async def abort(self, session_id: str) -> None:
        """中断指定会话的处理。"""
```

**分发流程：**

```
Envelope
   │
   ▼
┌──────────────────┐
│ 1. 意图路由       │  PING → pong / ABORT → abort / COMMAND → command_handler
│    (intent)      │  CHAT → 继续 ↓
└────────┬─────────┘
         ▼
┌──────────────────┐
│ 2. 解析目标 Agent │  agent_id > agent_name > DEFAULT_AGENT_ID
│    _resolve_agent│  → AgentInfo(id, name, type, persona)
└────────┬─────────┘
         ▼
┌──────────────────┐
│ 3. 构建 Identity  │  从 Envelope 提取 session_id, channel_type, user_id 等
│    + Context     │  创建 AgentContext，设置 contextvars
└────────┬─────────┘
         ▼
┌──────────────────┐
│ 4. 会话管理       │  SessionManager.get_or_create(session_id)
│                  │  加载历史消息
└────────┬─────────┘
         ▼
┌──────────────────┐
│ 5. 技能调度       │  SkillCommandResolver 解析 /command
│    (可选)        │  SkillPromptRewriter 注入技能上下文
└────────┬─────────┘
         ▼
┌──────────────────┐
│ 6. AgentBridge   │  构建 AgentCoreConfig
│    .run()        │  调用 agent_loop()
│                  │  yield GatewayEvent
└──────────────────┘
```

### 3.3 Agent Core 桥接器（AgentBridge）

**`agent_bridge.py`** — 将现有 `websocket.py` 中的 Agent 编排逻辑抽取到此处：

```python
class AgentBridge:
    """Agent Core 桥接器。

    封装 AgentCoreConfig 的创建和 agent_loop 的调用，
    是 Gateway 与 Agent Core 之间的唯一连接点。

    从现有 websocket.py 中的 create_agent_config() 和
    消息处理逻辑迁移而来。
    """

    def create_config(self, agent: AgentInfo | None = None) -> AgentCoreConfig:
        """根据 Agent 信息创建配置。

        不同 Agent 可以有：
        - 不同的 system_prompt（基于 agent_persona）
        - 不同的工具集
        - 不同的模型配置（未来扩展）
        """

    async def run(
        self,
        content: str,
        session_id: str,
        agent: AgentInfo | None = None,
        images: list[tuple[str, str]] | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """执行 Agent Loop 并产出网关事件。"""
```

### 3.4 响应事件（GatewayEvent）

**`response.py`** — 协议无关的响应事件：

```python
@dataclass
class GatewayEvent:
    """Gateway 层的统一响应事件。

    各端点负责将 GatewayEvent 转换为自己协议的格式：
    - WebChat: 转为 WebSocket JSON
    - CLI: 转为终端输出
    - Channel: 转为各平台 API 格式
    """
    type: GatewayEventType
    data: dict[str, Any] = field(default_factory=dict)

    # 响应来源 Agent 信息
    agent_id: str | None = None
    agent_name: str | None = None

class GatewayEventType(str, Enum):
    TEXT_CHUNK = "text_chunk"         # 流式文本片段
    THINKING_CHUNK = "thinking_chunk" # 思考过程片段
    MESSAGE_END = "message_end"       # 消息完成
    TOOL_CALL = "tool_call"           # 工具调用开始
    TOOL_RESULT = "tool_result"       # 工具调用结果
    ERROR = "error"                   # 错误
    PONG = "pong"                     # 心跳响应
    AGENT_START = "agent_start"       # Agent 开始
    AGENT_END = "agent_end"           # Agent 结束
```

### 3.5 AgentInfo 值对象

```python
@dataclass(frozen=True)
class AgentInfo:
    """Agent 信息值对象（Gateway 层使用）。

    从 DB 的 Agent ORM 模型转换而来，
    Gateway 层通过此对象获取 Agent 信息，
    不直接依赖 SQLAlchemy 模型。
    """
    agent_id: str
    agent_name: str
    agent_type: str           # "main" | "partner" | "sub"
    agent_persona: str = ""   # Agent 人设（用于构建 system_prompt）
```

### 3.6 与现有 WebSocket 的关系（迁移策略）

**不是替换，而是分层**。现有 `agent_core/api/websocket.py` 将被重构为：

```
重构前:
  WebSocket → [编排逻辑 + Agent调用] (全在 websocket.py)

重构后:
  WebSocket → Envelope → GatewayDispatcher → AgentBridge → agent_loop
  (websocket.py)  (gateway/)                              (agent_core/)
```

`websocket.py` 瘦身为纯协议层：只负责 WS 连接管理、JSON 解析、Envelope 封装、GatewayEvent → WS JSON 转换。

---

## 四、CLI 设计

### 4.1 目录结构

```
cli/                              # 独立顶层目录，与 backend/frontend 平级
├── __init__.py
├── main.py                       # CLI 入口 (typer)
├── commands/                     # 命令组
│   ├── __init__.py
│   ├── chat.py                   # 对话命令: x-agent chat
│   ├── config.py                 # 配置管理: x-agent config show/set
│   ├── tools.py                  # 工具管理: x-agent tools list/info
│   ├── session.py                # 会话管理: x-agent session list/clear
│   ├── agent.py                  # Agent 管理: x-agent agent list/info/create
│   └── status.py                 # 状态查看: x-agent status
├── adapters/                     # CLI 专用适配器
│   ├── __init__.py
│   ├── gateway_client.py         # Gateway HTTP/WS 客户端
│   └── output_renderer.py        # 终端输出渲染（Rich）
├── config.py                     # CLI 本地配置
└── pyproject.toml                # CLI 独立依赖
```

### 4.2 两种运行模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **Remote 模式** | CLI 作为客户端，通过 HTTP/WS 连接已运行的 Backend | 生产环境、远程服务器 |
| **Embedded 模式** | CLI 直接 import Gateway 模块，进程内调用 | 本地开发、单机部署 |

### 4.3 核心命令设计

```bash
# 对话（核心功能）
x-agent chat                      # 进入交互式对话
x-agent chat "今天天气怎么样"       # 单次对话
x-agent chat --session <id>       # 恢复指定会话
x-agent chat --new                # 强制新建会话
x-agent chat --agent "虾铁蛋"     # 指定 Agent（按名称）
x-agent chat --agent-id <id>      # 指定 Agent（按 ID）

# Agent 管理
x-agent agent list                # 列出所有 Agent
x-agent agent info <agent_id>     # 查看 Agent 详情
x-agent agent create --name "助手B" --type partner  # 创建新 Agent

# 配置管理
x-agent config show               # 显示当前配置
x-agent config set <key> <value>  # 修改配置项
x-agent config reload             # 热重载配置

# 工具管理
x-agent tools list                # 列出所有可用工具
x-agent tools info <name>         # 查看工具详情
x-agent tools enable/disable <n>  # 启用/禁用工具

# 会话管理
x-agent session list              # 列出所有会话
x-agent session clear             # 清除会话历史

# 系统状态
x-agent status                    # 查看系统状态
```

### 4.4 交互式对话流程

```
用户输入
   │
   ▼
┌──────────────────┐
│ CLI InputHandler │  readline / prompt_toolkit
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 封装 Envelope    │  channel_type=CLI, channel_protocol=REST_API
│                  │  intent=CHAT
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ GatewayClient    │  Remote: HTTP POST /api/v1/gateway/chat (SSE)
│                  │  Embedded: 直接调用 dispatcher.dispatch()
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ OutputRenderer   │  Rich: Markdown渲染、Spinner、进度条
│                  │  工具调用: 折叠显示
│                  │  思考过程: 灰色斜体
└──────────────────┘
```

---

## 五、Channel 预留设计

本阶段只定义接口，不做实现：

```
backend/src/channel/
├── __init__.py
├── base.py                       # ChannelAdapter 抽象基类
└── registry.py                   # Channel 注册表
```

```python
class ChannelAdapter(ABC):
    """外部消息通道适配器基类。

    每个 Channel（钉钉/微信/Telegram/飞书）实现此接口，
    负责：
    1. 接收外部平台的 Webhook/长轮询消息
    2. 转换为 Envelope
    3. 将 GatewayEvent 转换为平台回复格式
    """

    @abstractmethod
    def channel_type(self) -> ChannelType:
        """返回渠道类型。"""

    @abstractmethod
    async def start(self) -> None:
        """启动渠道监听。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道监听。"""

    @abstractmethod
    async def to_envelope(self, raw_message: Any) -> Envelope:
        """将平台原始消息转换为统一信封。"""

    @abstractmethod
    async def render_response(self, event: GatewayEvent) -> Any:
        """将 Gateway 事件转换为平台回复格式。"""
```

---

## 六、完整目录结构（重构后）

```
x-agent/
├── backend/
│   ├── src/
│   │   ├── gateway/                    # 🆕 网关层
│   │   │   ├── __init__.py
│   │   │   ├── envelope.py             # 统一消息信封
│   │   │   ├── dispatcher.py           # 请求分发器
│   │   │   ├── response.py             # 响应事件定义
│   │   │   ├── agent_bridge.py         # Agent Core 桥接
│   │   │   └── errors.py              # 网关错误
│   │   │
│   │   ├── channel/                    # 🆕 渠道层（预留）
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # ChannelAdapter 基类
│   │   │   └── registry.py            # 渠道注册表
│   │   │
│   │   ├── agent_core/                 # ✅ 不变 - 核心层
│   │   │   ├── api/
│   │   │   │   └── websocket.py        # 🔄 瘦身: 纯 WS 协议层
│   │   │   ├── agent_loop.py
│   │   │   ├── agent.py
│   │   │   ├── ports/
│   │   │   ├── adapters/
│   │   │   └── ...
│   │   │
│   │   ├── api/                        # 🔄 新增 Gateway REST 端点
│   │   │   └── v1/
│   │   │       └── gateway.py          # 🆕 /api/v1/gateway/chat (SSE)
│   │   │
│   │   ├── conversation/              # ✅ 不变
│   │   ├── memory/                    # ✅ 不变
│   │   ├── services/                  # ✅ 不变
│   │   ├── config/                    # ✅ 不变
│   │   └── main.py                    # 🔄 注册 Gateway 路由
│   │
│   └── pyproject.toml
│
├── cli/                                # 🆕 CLI 端（独立包）
│   ├── __init__.py
│   ├── main.py
│   ├── commands/
│   │   ├── chat.py
│   │   ├── config.py
│   │   ├── tools.py
│   │   ├── session.py
│   │   ├── agent.py
│   │   └── status.py
│   ├── adapters/
│   │   ├── gateway_client.py
│   │   └── output_renderer.py
│   ├── config.py
│   └── pyproject.toml
│
├── frontend/                          # ✅ 不变
└── workspace/                         # ✅ 不变
```

---

## 七、数据流对比

### 重构前（WebChat Only）

```
Browser → WebSocket → websocket.py → [编排] → agent_loop → [事件] → WebSocket → Browser
```

### 重构后（多端统一）

```
Browser ──► WebSocket ──► websocket.py ──┐
                                         │
CLI ────► HTTP SSE ──► gateway.py ───────┤
                                         ├──► Envelope ──► GatewayDispatcher
DingTalk ► Webhook ──► dingtalk.py ──────┤        │
                                         │        ▼
WeChat ──► Webhook ──► wechat.py ────────┘   AgentBridge
                                                  │
                                                  ▼
                                             agent_loop()
                                                  │
                                                  ▼
                                            GatewayEvent
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                              WS JSON        SSE Stream    Platform API
                              (Browser)      (CLI)         (DingTalk/...)
```

---

## 八、多 Agent 支持

### 8.1 Envelope Agent 路由

Envelope 携带 `agent_id` 和 `agent_name`，GatewayDispatcher 通过 `_resolve_agent()` 解析目标 Agent：

**路由优先级**：`agent_id` > `agent_name` > `DEFAULT_AGENT_ID`

### 8.2 AgentInfo 值对象

Gateway 层使用 `AgentInfo` 值对象（而非 ORM 模型）传递 Agent 信息：

```python
@dataclass(frozen=True)
class AgentInfo:
    agent_id: str
    agent_name: str
    agent_type: str           # "main" | "partner" | "sub"
    agent_persona: str = ""
```

### 8.3 GatewayEvent 携带 Agent 信息

每个 `GatewayEvent` 都携带 `agent_id` 和 `agent_name`，上游端点可以知道响应来自哪个 Agent。

### 8.4 未来多 Agent 协作扩展路径

| 场景 | 实现方式 |
|------|----------|
| **Agent 切换** | 用户通过 `@agent_name` 切换目标 Agent |
| **Agent 委派** | 主 Agent 通过 `Identity.derive(agent_type=SUB)` 派生子 Agent |
| **Agent 协作** | 多个 Agent 共享同一 `session_id`，各自有独立的 `agent_id` |
| **Agent 配置隔离** | 不同 Agent 可绑定不同的模型、工具集、persona |
| **Agent 注册** | 通过 Admin API 或 CLI 动态创建新 Agent |

---

## 九、与现有系统的兼容性

| 现有模块 | 兼容方式 |
|----------|----------|
| `Identity` 模型 | 完全复用，`ChannelType` 和 `ChannelProtocol` 已预留 CLI/DingTalk 等枚举值 |
| `AgentContext` | 工厂方法 `for_websocket()` 已存在，新增 `for_gateway()` |
| `AgentCoreConfig` | 不变，Gateway 通过 AgentBridge 构建 |
| `SessionManager` | 不变，所有端点共享同一套会话管理 |
| `MemoryManager` | 不变，记忆系统与消息入口无关 |
| `Agent` ORM | 已有 `agent_id` + `agent_name`，Gateway 通过 `AgentDAO` 查询 |
| `ChatSession` | 已有 `agent_id` 外键，Session 天然绑定到 Agent |
| `Channel` ORM | `(user_id, agent_id, channel_type)` 唯一约束已支持多渠道多 Agent |
| `DEFAULT_AGENT_ID` | 当 Envelope 未指定 agent_id 时回退到默认 Agent，完全向后兼容 |

---

## 十、迁移策略（渐进式，零停机）

| 阶段 | 内容 | 影响 |
|------|------|------|
| **Phase 1** | 创建 `gateway/` 模块，定义 Envelope + GatewayEvent + Dispatcher + AgentBridge | 无影响，纯新增 |
| **Phase 2** | WebSocket 端点改为通过 Gateway 调用 + 新增 SSE 端点 | WebChat 走新链路 |
| **Phase 3** | Channel 预留接口 + CLI 基础结构 | 新增独立入口 |
| **Phase 4** | CLI 功能实现 | CLI 可用 |

每个阶段独立可测试、可回滚。

---

## 十一、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| CLI 独立包 vs 内嵌 | 独立顶层目录 `cli/` | CLI 有独立依赖（typer/rich），不应污染 backend |
| CLI 框架 | `typer` + `rich` | typer 基于 click，类型安全；rich 终端渲染能力强 |
| CLI 通信协议 | SSE (Remote) / 直接调用 (Embedded) | SSE 支持流式，比轮询高效；Embedded 零网络开销 |
| Gateway 位置 | `backend/src/gateway/` | 与 agent_core 同进程，避免额外 IPC 开销 |
| Envelope vs 直接用 AgentMessage | 新建 Envelope | AgentMessage 是 agent_core 内部类型，Gateway 需要携带渠道元数据 |
| Channel 本阶段 | 仅定义 ABC + Registry | 避免过度设计，接口稳定后再实现 |
