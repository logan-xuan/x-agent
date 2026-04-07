# Runtime Interfaces 详细方案

> 范围：新的 runtime 在 Python 代码中的模块边界、核心接口、状态对象、协议定义，以及与现有代码的挂接方式。

---

## 1. 目标

这份文档回答两个问题：

1. 新 runtime 在代码里应长成什么样
2. 现有 `agent_core / conversation / services / gateway` 如何接到这些新接口上

这里的重点不是讨论业务行为，而是把实现边界定死，避免后续继续把逻辑散在多个模块里。

---

## 2. 新 package 结构

建议新增独立 package：

```text
backend/src/runtime/
├── __init__.py
├── types.py
├── turn/
│   ├── __init__.py
│   ├── controller.py
│   ├── budget.py
│   ├── assessment.py
│   ├── tool_governor.py
│   ├── finish_reason.py
│   └── invoker.py
├── context/
│   ├── __init__.py
│   ├── builder.py
│   ├── history_view.py
│   ├── artifact_store.py
│   ├── compression_pipeline.py
│   ├── compression_verifier.py
│   └── memory_flush.py
├── session/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── store.py
│   ├── lane_scheduler.py
│   ├── route_resolver.py
│   ├── spawn_manager.py
│   ├── announcement_manager.py
│   └── lifecycle.py
└── adapters/
    ├── agent_core_adapter.py
    ├── conversation_adapter.py
    ├── compression_adapter.py
    └── gateway_adapter.py
```

### 2.1 为什么单独建 `runtime/`

原因：

- 不污染现有 `agent_core/`
- 允许新旧架构并行一段时间
- 能通过 adapter 逐步替换现有入口

---

## 3. 基础类型

建议将跨子系统共享的数据类型统一放到：

- `backend/src/runtime/types.py`

### 3.1 关键类型

```python
from dataclasses import dataclass, field
from typing import Literal, Any


FinishReason = Literal[
    "done_definition_satisfied",
    "max_turns",
    "max_wall_time",
    "max_tokens",
    "max_cost",
    "diminishing_returns",
    "breaker",
    "controller_abort",
    "best_effort_budget_stop",
]


@dataclass
class TaskFrame:
    objective: str
    done_definition: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    deliverable: str = ""
    working_plan: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    active_artifacts: list[str] = field(default_factory=list)


@dataclass
class RouteMeta:
    channel: str
    account_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    topic_id: str | None = None
    origin_message_id: str | None = None


@dataclass
class SessionDescriptor:
    session_key: str
    session_id: str
    parent_session_key: str | None = None
    lane: Literal["main", "followup", "subagent", "cron", "background_tool"] = "main"
    model_profile: str = "default"
    budget_profile: str = "default"
    summary_ref: str | None = None
    memory_ref: str | None = None
    route: RouteMeta | None = None
    status: Literal["active", "idle", "compacted", "archived"] = "active"


@dataclass
class ArtifactRef:
    id: str
    kind: Literal["web", "bash", "search", "file", "tool", "summary"]
    title: str
    preview: str
    location: str | None = None
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## 4. Turn 子系统接口

### 4.1 TurnController

```python
from typing import Protocol


class TurnController(Protocol):
    async def run(self, request: "TurnRequest") -> "TurnResult":
        ...
```

### 4.2 TurnRequest / TurnResult

```python
@dataclass
class TurnRequest:
    session: SessionDescriptor
    user_input: str
    task_frame: TaskFrame
    route: RouteMeta
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    kind: Literal["final", "continue", "spawn", "abort", "compact"]
    finish_reason: FinishReason | None = None
    output_text: str | None = None
    updated_task_frame: TaskFrame | None = None
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    spawn_packet: "SpawnPacket | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 4.3 BudgetManager

```python
class BudgetManager(Protocol):
    def evaluate(self, state: "TurnState") -> "BudgetDecision":
        ...
```

### 4.4 AssessmentEngine

```python
class AssessmentEngine(Protocol):
    def assess(self, state: "TurnState") -> "LoopAssessment":
        ...
```

### 4.5 ToolGovernor

```python
class ToolGovernor(Protocol):
    def validate_plan(self, plan: "ToolExecutionPlan", state: "TurnState") -> "GovernedToolPlan":
        ...

    def register_result(self, state: "TurnState", result: "ToolExecutionResult") -> None:
        ...
```

### 4.6 适配现有代码

第一阶段不直接替换：

- `agent_core/agent_loop.py`
- `agent_core/tool_executor.py`

而是增加 adapter：

- `runtime/adapters/agent_core_adapter.py`

其职责：

- 将现有 loop 输入映射为 `TurnRequest`
- 将 `TurnResult` 映射回当前 websocket / agent 输出模型

---

## 5. Context 子系统接口

### 5.1 ContextBuilder

```python
class ContextBuilder(Protocol):
    async def build(self, request: "ContextBuildRequest") -> "ContextBuildResult":
        ...
```

### 5.2 ContextBuildRequest / Result

```python
@dataclass
class ContextBuildRequest:
    session: SessionDescriptor
    task_frame: TaskFrame
    raw_messages: list[Any]
    prompt_mode: Literal["full", "minimal", "none"] = "full"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBuildResult:
    system_prompt: str
    active_messages: list[Any]
    active_artifacts: list[ArtifactRef]
    estimated_input_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 5.3 ArtifactStore

```python
class ArtifactStore(Protocol):
    async def put(self, item: "ArtifactWriteRequest") -> ArtifactRef:
        ...

    async def get(self, artifact_id: str) -> ArtifactRef | None:
        ...
```

### 5.4 CompressionPipeline

```python
class CompressionPipeline(Protocol):
    async def run(self, ctx: "CompressionContext") -> "CompressionResult":
        ...

    async def run_emergency(self, ctx: "CompressionContext") -> "CompressionResult":
        ...
```

### 5.5 CompressionVerifier

```python
class CompressionVerifier(Protocol):
    def verify(self, request: "CompressionVerifyRequest") -> "CompressionPostCheck":
        ...
```

### 5.6 适配现有代码

优先复用而不是重写：

- `conversation/system_prompt_builder.py`
- `services/context/`
- `services/compression/`
- `memory/manager.py`

在 `runtime/adapters/conversation_adapter.py` 和 `runtime/adapters/compression_adapter.py` 中做桥接。

---

## 6. Session 子系统接口

### 6.1 SessionOrchestrator

```python
class SessionOrchestrator(Protocol):
    async def resolve_or_create(self, event: "GatewayEvent") -> SessionDescriptor:
        ...

    async def enqueue_turn(self, session: SessionDescriptor, request: TurnRequest) -> None:
        ...

    async def spawn_child(self, parent: SessionDescriptor, packet: "SpawnPacket") -> SessionDescriptor:
        ...

    async def archive(self, session_key: str) -> None:
        ...
```

### 6.2 SessionStore

```python
class SessionStore(Protocol):
    async def get(self, session_key: str) -> SessionDescriptor | None:
        ...

    async def put(self, session: SessionDescriptor) -> None:
        ...

    async def patch(self, session_key: str, values: dict[str, Any]) -> SessionDescriptor:
        ...
```

### 6.3 LaneScheduler

```python
class LaneScheduler(Protocol):
    async def enqueue(self, lane: str, fn: "AsyncCallable") -> None:
        ...

    def get_depth(self, lane: str) -> int:
        ...
```

### 6.4 RouteResolver

```python
class RouteResolver(Protocol):
    async def resolve(self, event: "GatewayEvent") -> RouteMeta:
        ...
```

### 6.5 SpawnPacket / ChildResult

```python
@dataclass
class SpawnPacket:
    objective: str
    deliverable: str
    constraints: list[str] = field(default_factory=list)
    parent_summary: str = ""
    selected_artifacts: list[str] = field(default_factory=list)
    tool_allowlist: list[str] = field(default_factory=list)
    budget_profile: str = "child-default"
    timeout_ms: int = 0


@dataclass
class ChildResult:
    status: Literal["success", "error", "timeout"]
    summary: str
    unresolved: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
```

### 6.6 适配现有代码

优先从这些入口桥接：

- `gateway/dispatcher.py`
- `gateway/agent_invoker.py`
- `gateway/session_resolver.py`
- `gateway/message_bus.py`
- `api/v1/sessions.py`

通过：

- `runtime/adapters/gateway_adapter.py`

先把 session routing 和 enqueue 逻辑纳入新 orchestrator，再逐步替换现有分支。

---

## 7. 配置读取接口

虽然配置模型由 `06-config-schema.md` 定义，但运行时代码建议使用一个统一 reader：

```python
class RuntimeConfigProvider(Protocol):
    def get_turn_profile(self, name: str) -> "TurnBudgetProfile":
        ...

    def get_compression_profile(self, name: str) -> "CompressionProfile":
        ...

    def get_session_profile(self, name: str) -> "SessionProfile":
        ...
```

这样 runtime 各模块不直接依赖原始 Pydantic model 结构。

---

## 8. 事件与 telemetry 接口

### 8.1 RuntimeEventBus

```python
class RuntimeEventBus(Protocol):
    async def publish(self, event: "RuntimeEvent") -> None:
        ...
```

### 8.2 RuntimeEvent

```python
@dataclass
class RuntimeEvent:
    type: str
    session_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0
```

建议至少覆盖：

- turn start/end
- budget warning/stop
- tool invocation/result
- compression start/end/fallback
- session create/archive
- child spawn/complete

---

## 9. 目录级改造建议

### 9.1 第一阶段新增，不替换

先新增：

- `backend/src/runtime/`

但不立刻删除：

- `agent_core/`
- `conversation/`
- `services/compression/`
- `gateway/`

### 9.2 第二阶段桥接

通过 adapter 让新接口接入旧实现：

- `agent_core_adapter`
- `conversation_adapter`
- `compression_adapter`
- `gateway_adapter`

### 9.3 第三阶段替换入口

当接口稳定后，再逐步替换实际入口：

- websocket / rest -> orchestrator
- agent loop -> turn controller
- system prompt / context -> context builder

---

## 10. 验收标准

接口层设计完成后，应满足：

- 所有核心子系统都有明确 protocol 或抽象接口
- 共享类型统一放在 `runtime/types.py`
- 新旧代码之间有清晰 adapter 边界
- 后续实现工作可以按接口并行推进

如果这些边界不先定死，后续继续做功能只会把现有模块耦合得更深。
