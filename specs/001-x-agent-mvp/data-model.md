# Data Model: X-Agent MVP

**Feature**: X-Agent MVP  
**Created**: 2026-02-14  
**Related**: [spec.md](./spec.md), [plan.md](./plan.md)

## Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐
│     Session     │◄──────┤     Message     │
├─────────────────┤   1:n ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ title           │       │ session_id (FK) │
│ created_at      │       │ role            │
│ updated_at      │       │ content         │
│ message_count   │       │ created_at      │
└─────────────────┘       └─────────────────┘
```

## Entities

### Session (会话)

代表一次用户与 Agent 的对话会话。

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String (UUID) | PK, Indexed | 会话唯一标识 |
| title | String | Max 200 chars, Nullable | 会话标题（可由 AI 生成或用户设置） |
| created_at | DateTime | Indexed | 会话创建时间 |
| updated_at | DateTime | Indexed | 最后更新时间 |
| message_count | Integer | Default 0 | 消息数量缓存 |

**业务规则**:
- 创建会话时自动生成 UUID
- 首次用户消息发送后，AI 自动生成会话标题（基于内容摘要）
- 每次新增消息时更新 `updated_at` 和 `message_count`

---

### Message (消息)

代表会话中的一条消息。

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String (UUID) | PK, Indexed | 消息唯一标识 |
| session_id | String (UUID) | FK → Session.id, Indexed | 所属会话 |
| role | Enum | user/assistant/system | 消息发送者角色 |
| content | Text | Not null | 消息内容 |
| created_at | DateTime | Indexed | 消息创建时间 |
| metadata | JSON | Nullable | 扩展元数据（token 用量、模型名称等） |

**业务规则**:
- `role` 只能是 `user`、`assistant` 或 `system`
- `content` 不能为空字符串
- 删除 Session 时级联删除关联的 Messages
- 按 `created_at` 升序排列即为对话历史

---

### Config (配置)

系统配置，存储在 YAML 文件中，运行时加载到内存。采用高内聚设计，支持热重载。

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| models | Array[ModelConfig] | At least 1 | 模型配置列表 |
| server | ServerConfig | Required | 服务配置 |
| logging | LoggingConfig | Required | 日志配置 |

#### ModelConfig

厂商无关的模型配置设计，支持任意兼容 OpenAI 接口的提供商。

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| name | String | Required, Unique | 配置名称（如 primary, backup-1） |
| provider | Enum | openai/bailian/custom | 提供商类型（custom 用于其他兼容 OpenAI 的提供商） |
| base_url | String | URL format | API 基础地址 |
| api_key | String | Required, Secret | API 密钥（加密存储，日志脱敏） |
| model_id | String | Required | 模型标识（如 gpt-3.5-turbo, qwen-turbo） |
| is_primary | Boolean | Exactly one true | 是否主模型（有且仅有一个主模型） |
| timeout | Float | Default 30.0 | 请求超时时间（秒） |
| max_retries | Integer | Default 2, Range 0-5 | 请求失败最大重试次数 |
| priority | Integer | Default 0 | 备用模型优先级（数值越小优先级越高） |

**业务规则**:
- `models` 列表必须包含至少一个配置
- 有且仅有一个模型的 `is_primary` 为 true
- `api_key` 必须加密存储，日志中脱敏显示
- 主模型故障时，按 `priority` 顺序尝试备用模型

#### ServerConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| host | String | "0.0.0.0" | 监听地址 |
| port | Integer | 8000, Range 1-65535 | 服务端口 |
| cors_origins | Array[String] | ["http://localhost:5173"] | 允许的 CORS 源 |
| reload | Boolean | false | 是否启用自动重载（开发模式） |

#### LoggingConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| level | Enum | "INFO" | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| format | Enum | "json" | 日志格式 (json/text) |
| file | String | "logs/x-agent.log" | 日志文件路径 |
| max_size | String | "10MB" | 单个日志文件最大大小 |
| backup_count | Integer | 5 | 保留的备份文件数量 |
| console | Boolean | true | 是否输出到控制台 |

---

## State Transitions

### Session 生命周期

```
[Created] ──► [Active] ──► [Archived]
    │              │
    │              ▼
    │         [Deleted]
    │
    ▼
[Deleted]
```

- **Created**: 会话创建，等待第一条消息
- **Active**: 有消息交互的活跃会话
- **Archived**: 长期未使用，可被归档（MVP 阶段不实现）
- **Deleted**: 用户删除会话

---

## Validation Rules

### Session

1. `title` 最大长度 200 字符
2. `created_at` 和 `updated_at` 必须是有效的 ISO 8601 时间戳
3. `message_count` 必须是非负整数

### Message

1. `content` 不能为空字符串（允许空白字符，但 trim 后不能为空）
2. `content` 最大长度 100,000 字符（约 25k tokens）
3. `role` 必须是预定义枚举值之一
4. `metadata` 必须是有效的 JSON 对象

---

## Indexes

| Table | Fields | Type | Purpose |
|-------|--------|------|---------|
| Session | id | Primary Key | 唯一标识查找 |
| Session | updated_at | B-Tree | 会话列表排序 |
| Message | id | Primary Key | 唯一标识查找 |
| Message | session_id | B-Tree | 会话消息查询 |
| Message | created_at | B-Tree | 消息历史排序 |

---

## Storage Considerations

### SQLite 配置

- 使用 WAL (Write-Ahead Logging) 模式提升并发性能
- 启用外键约束 (`PRAGMA foreign_keys = ON`)
- 设置合理的缓存大小 (`PRAGMA cache_size = -64000`)

### 数据保留策略 (MVP)

- 不自动删除历史数据
- 提供手动删除会话功能
- 后续版本考虑自动归档长期未使用会话

---

## Migration Strategy

### 初始版本 (v1.0)

```sql
-- 创建 Session 表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_sessions_updated_at ON sessions(updated_at);

-- 创建 Message 表
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```
