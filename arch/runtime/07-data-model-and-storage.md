# Runtime Data Model And Storage 详细方案

> 范围：session、message、transcript、artifact、summary chain、session state、compression event 的目标持久化模型，以及与现有数据库/存储实现的迁移方式。

---

## 1. 目标

这份文档解决的问题是：

- runtime 关键状态应该存什么
- 存在哪一层
- 哪些是原始记录，哪些是运行时快照，哪些是派生视图
- 如何从当前 `sessions / messages / compression_events` 逐步迁移到目标结构

核心原则：

- 原始记录与运行时视图分离
- 可回放数据与可推理数据分离
- 结构化 summary 与原始 transcript 并存

---

## 2. 当前代码基线

当前已存在的核心模型和管理器：

- [session.py](/Users/xuan.lx/Documents/x-agent/backend/src/models/session.py)
- [message.py](/Users/xuan.lx/Documents/x-agent/backend/src/models/message.py)
- [compression.py](/Users/xuan.lx/Documents/x-agent/backend/src/models/compression.py)
- [conversation/session.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/session.py)

### 2.1 当前已有表

#### `sessions`

当前字段大致包括：

- `id`
- `title`
- `agent_id`
- `status`
- `created_at`
- `updated_at`
- `message_count`

问题：

- 只有“聊天会话”概念，没有 runtime 级 `session_key / lane / parent / route / profile`
- 无法表达 child session、archive、route、summaryRef 等

#### `messages`

当前字段大致包括：

- `id`
- `session_id`
- `role`
- `content`
- `created_at`
- `metadata_json`

问题：

- 只适合简单 chat message
- 无法清晰表达 artifact ref、tool result、summary boundary、runtime attachment

#### `compression_events`

当前字段大致包括：

- 原始消息数量
- 压缩后数量
- token 数
- 压缩前后的原始消息 JSON

问题：

- 更偏审计记录，而不是 runtime 压缩链的一等模型

---

## 3. 目标存储层分工

建议将 runtime 存储分成 5 类：

| 存储类型 | 作用 |
|---|---|
| `Session Store` | session 生命周期与配置快照 |
| `Transcript Store` | 原始消息与原始事件 |
| `Summary Store` | compaction / collapse / memory flush 产生的结构化摘要 |
| `Artifact Store` | 大工具输出、网页、抓取结果、代码块集合 |
| `Telemetry Store` | 压缩事件、预算命中、turn 结束原因、lane 深度 |

---

## 4. Session Store 目标模型

### 4.1 SessionRecord

```python
@dataclass
class SessionRecord:
    session_key: str
    session_id: str
    parent_session_key: str | None = None
    root_session_key: str | None = None
    title: str | None = None
    agent_id: str | None = None
    lane: Literal["main", "followup", "subagent", "cron", "background_tool"] = "main"
    status: Literal["active", "idle", "compacted", "archived", "closed"] = "active"
    model_profile: str = "default"
    budget_profile: str = "default"
    compression_profile: str = "balanced"
    route_ref: str | None = None
    active_transcript_id: str | None = None
    latest_summary_id: str | None = None
    latest_state_snapshot_id: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    archived_at: float | None = None
```

### 4.2 为什么需要 `session_key` 和 `session_id`

- `session_key`：逻辑会话身份，长期稳定
- `session_id`：当前具体 transcript / state 版本

用途：

- session reset 不会破坏逻辑会话身份
- 允许保留历史 transcript 版本
- 便于 child session / announce / resume

### 4.3 兼容现有 `models.session.Session`

迁移建议：

- 短期保留现有 `Session.id` 作为 `session_id`
- 新增 `session_key`
- 后续逐步把业务层从 `session_id` 语义切到 `session_key`

---

## 5. Transcript Store 目标模型

### 5.1 原始消息模型

runtime 不应只用 `role + content`。

建议抽象为：

```python
@dataclass
class TranscriptEntry:
    entry_id: str
    session_id: str
    turn_index: int
    kind: Literal[
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "system_message",
        "attachment",
        "summary_boundary",
    ]
    role: str | None = None
    text: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: float = 0.0
```

### 5.2 为什么不再直接依赖 `messages`

原因：

- tool call / tool result 不是普通 chat message
- summary boundary 不是普通 message
- child session result / attachment / runtime notice 也不是普通 message

现有 `models.message.Message` 可保留，但应逐步升级为更通用的 transcript entry 模型。

### 5.3 建议持久化形态

建议支持两种形态：

- 数据库行存储
- JSONL transcript 文件

理由：

- DB 便于查询、聚合、过滤
- JSONL 便于审计、导出、回放

---

## 6. Summary Store 目标模型

### 6.1 SummaryRecord

```python
@dataclass
class SummaryRecord:
    summary_id: str
    session_id: str
    summary_type: Literal["microcompact", "collapse", "autocompact", "memory_flush", "child_result"]
    based_on_entry_ids: list[str]
    objective: str
    summary: str
    decisions: list[str]
    open_questions: list[str]
    read_files: list[str]
    modified_files: list[str]
    recent_failures: list[str]
    artifact_refs: list[str]
    created_at: float = 0.0
```

### 6.2 Summary Chain

同一个 session 可以拥有多条 summary，形成 chain：

```text
raw transcript prefix
-> collapse summary
-> autocompact summary
-> later active history
```

### 6.3 为什么 summary 必须单独存

原因：

- summary 是 runtime 一等对象，不只是压缩后字符串
- 需要单独引用、回放、校验、追踪
- 后续 child result / announce 也可以落成 summary

---

## 7. Artifact Store 目标模型

### 7.1 ArtifactRecord

```python
@dataclass
class ArtifactRecord:
    artifact_id: str
    session_id: str
    source_entry_id: str | None
    kind: Literal["web", "bash", "search", "file", "tool", "summary"]
    title: str
    preview: str
    body_text: str | None = None
    body_json: dict[str, Any] | None = None
    location: str | None = None
    sha256: str | None = None
    created_at: float = 0.0
```

### 7.2 存储要求

- `preview` 必须足够短，可直接进上下文
- `body_text/body_json` 不默认进 active context
- 允许 dedupe，相同大结果可通过 hash 去重

### 7.3 与现有 `services/context/` 的关系

现有目录中已经有 artifact / session state / evidence 相关能力，应尽量保留实现，统一收敛成 `ArtifactStore` 和 `SessionStateStore` 接口。

---

## 8. Session State Snapshot 目标模型

### 8.1 StateSnapshot

这是最关键但当前最缺的一层。

```python
@dataclass
class SessionStateSnapshot:
    snapshot_id: str
    session_id: str
    turn_index: int
    task_frame_json: dict[str, Any]
    unresolved: list[str]
    active_artifact_refs: list[str]
    budget_usage_json: dict[str, Any]
    tool_usage_json: dict[str, int]
    last_finish_reason: str | None = None
    created_at: float = 0.0
```

### 8.2 作用

- resume 时直接恢复 task frame 与预算状态
- 避免从全量 transcript 重新推断 runtime 状态
- 为调试和可观测性提供回放点

---

## 9. Compression Event 目标模型

### 9.1 保留 `compression_events`，但角色调整

当前 `compression_events` 不应删除，但应收敛为 telemetry / audit 表，而不是业务主模型。

建议目标：

```python
@dataclass
class CompressionEventRecord:
    event_id: str
    session_id: str
    turn_index: int
    stage: Literal["persist", "aggregate_budget", "ttl_prune", "microcompact", "collapse", "autocompact", "memory_flush", "emergency"]
    tokens_before: int
    tokens_after: int
    freed_tokens: int
    affected_entry_ids: list[str]
    affected_artifact_ids: list[str]
    fallback_used: bool = False
    created_at: float = 0.0
```

---

## 10. 存储关系图

```text
SessionRecord
 ├── active_transcript_id -> TranscriptEntry[]
 ├── latest_summary_id -> SummaryRecord
 ├── latest_state_snapshot_id -> SessionStateSnapshot
 └── route_ref -> RouteRecord

TranscriptEntry
 ├── may create -> ArtifactRecord
 └── may be summarized into -> SummaryRecord

SummaryRecord
 └── referenced by -> SessionRecord / ActiveHistoryView

CompressionEventRecord
 └── audits -> SummaryRecord / TranscriptEntry / ArtifactRecord changes
```

---

## 11. Active History View 是派生视图，不落业务表

非常关键：

- `active history view` 不建议作为业务主表持久化
- 它应该是由：
  - `SessionStateSnapshot`
  - `SummaryRecord`
  - 最近 `TranscriptEntry`
  - `ArtifactRef`

动态构建出的派生结果

这样可以避免：

- 历史视图和原始 transcript 双重写入不一致
- 每次压缩都要重写一大堆业务表

---

## 12. 迁移策略

### 12.1 第一步：不动现有表，增加新表或新仓储层

建议：

- 保留 `sessions`
- 保留 `messages`
- 保留 `compression_events`
- 新增：
  - `session_state_snapshots`
  - `summary_records`
  - `artifact_records`
  - 可选 `route_records`

### 12.2 第二步：通过 repository 抽象访问

新增：

- `SessionRepository`
- `TranscriptRepository`
- `SummaryRepository`
- `ArtifactRepository`
- `StateSnapshotRepository`

让 runtime 代码不直接依赖 SQLAlchemy model。

### 12.3 第三步：逐步从 `messages` 升级到 transcript entry

短期：

- 可以继续从 `messages` 读 user/assistant 内容
- tool result / attachments / summary boundary 用 `metadata_json` 临时承载

中期：

- 引入独立 transcript entry 表

---

## 13. 与现有代码的映射关系

### 13.1 session

- 当前：`models/session.py` + `conversation/session.py`
- 目标：`SessionRepository + SessionRecord`

### 13.2 message / transcript

- 当前：`models/message.py`
- 目标：`TranscriptEntry` 仓储层

### 13.3 compression

- 当前：`models/compression.py`
- 目标：`CompressionEventRecord` 审计层

### 13.4 runtime state

- 当前：基本缺失
- 目标：`SessionStateSnapshot`

---

## 14. 验收标准

数据层方案完成后，应满足：

- session、transcript、summary、artifact、state snapshot 职责清晰
- active history 被明确定义为派生视图
- 新旧表之间有兼容迁移路径
- runtime 代码可以通过 repository 独立于 SQLAlchemy model 演进

如果这一层不先设计清楚，后续 controller / compression / session orchestration 很快会互相覆盖状态。
