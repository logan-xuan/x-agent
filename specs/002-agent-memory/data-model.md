# Data Model: AI Agent 记忆系统

**Feature**: 002-agent-memory | **Date**: 2026-02-14

## Entity Relationship Diagram

```
┌─────────────────┐     ┌─────────────────┐
│   SPIRIT.md     │     │   OWNER.md      │
│   (AI 人格)      │     │   (用户画像)     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
         ┌─────────────────────┐
         │   Context Builder   │
         │   (上下文构建器)     │
         └──────────┬──────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
         ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│   Daily Log     │   │  Long-term      │
│   (每日日志)     │   │  Memory         │
│   memory/*.md   │   │  MEMORY.md      │
└────────┬────────┘   └────────┬────────┘
         │                     │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │   Memory Entry      │
         │   (记忆条目)         │
         │   - UUID            │
         │   - Content         │
         │   - Embedding       │
         │   - Metadata        │
         └─────────────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │   Vector Store      │
         │   (sqlite-vss)      │
         └─────────────────────┘
```

## Core Entities

### 1. MemoryEntry (记忆条目)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | UUID | 唯一标识符 | PRIMARY KEY |
| content | TEXT | 记忆内容 | NOT NULL |
| content_type | ENUM | 类型: conversation/decision/summary/manual | NOT NULL |
| source_file | VARCHAR(255) | 来源文件路径 | NOT NULL |
| created_at | DATETIME | 创建时间 | NOT NULL, DEFAULT NOW |
| updated_at | DATETIME | 更新时间 | NOT NULL, DEFAULT NOW |
| embedding | BLOB | 向量嵌入 (384维 float32) | NULLABLE |
| metadata | JSON | 扩展元数据 (tags, session_id等) | NULLABLE |

**Validation Rules**:
- `content` 不能为空，最大长度 10000 字符
- `content_type` 必须是预定义枚举值
- `embedding` 维度必须为 384

**State Transitions**:
```
[创建] → conversation/decision/summary/manual
[更新] → updated_at 更新，embedding 重新计算
[删除] → 从文件和向量库同步删除
```

---

### 2. SpiritConfig (AI 人格配置)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| role | TEXT | 角色定位 | NOT NULL |
| personality | TEXT | 性格特征 | NOT NULL |
| values | JSON | 价值观列表 | NOT NULL |
| behavior_rules | JSON | 行为准则列表 | NOT NULL |
| file_path | VARCHAR(255) | 文件路径 | UNIQUE |
| last_modified | DATETIME | 最后修改时间 | NOT NULL |

**File Format** (SPIRIT.md):
```markdown
# AI 人格设定

## 角色定位
[角色描述]

## 性格特征
- 特征1
- 特征2

## 价值观
- 价值观1
- 价值观2

## 行为准则
- 准则1
- 准则2
```

---

### 3. OwnerProfile (用户画像)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| name | VARCHAR(100) | 用户姓名 | NOT NULL |
| age | INTEGER | 年龄 | NULLABLE |
| occupation | VARCHAR(200) | 职业 | NULLABLE |
| interests | JSON | 兴趣列表 | NOT NULL, DEFAULT [] |
| goals | JSON | 目标列表 | NOT NULL, DEFAULT [] |
| preferences | JSON | 偏好设置 | NOT NULL, DEFAULT {} |
| file_path | VARCHAR(255) | 文件路径 | UNIQUE |
| last_modified | DATETIME | 最后修改时间 | NOT NULL |

**File Format** (OWNER.md):
```markdown
# 用户画像

## 基本信息
- 姓名: 张三
- 年龄: 32
- 职业: 前端工程师

## 兴趣爱好
- 编程
- 咖啡
- 徒步旅行

## 当前目标
- 开发一款本地 AI 笔记工具

## 偏好设置
- 喜欢简洁 UI
- 不喜欢拿铁，只喝美式
```

---

### 4. DailyLog (每日日志)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| date | DATE | 日志日期 | PRIMARY KEY |
| file_path | VARCHAR(255) | 文件路径 | UNIQUE |
| entries | JSON | 当日记忆条目 ID 列表 | NOT NULL, DEFAULT [] |
| summary | TEXT | 当日摘要 | NULLABLE |
| created_at | DATETIME | 创建时间 | NOT NULL |

**File Format** (memory/2026-02-14.md):
```markdown
# 2026-02-14 日志

## 摘要
[AI 生成的当日摘要]

## 记录条目

### 10:30 - 决策
用户决定使用 React 作为前端框架

### 14:00 - 对话
讨论了数据库选型，最终选择 SQLite
```

---

### 5. ToolDefinition (工具定义)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| name | VARCHAR(100) | 工具名称 | PRIMARY KEY |
| description | TEXT | 功能描述 | NOT NULL |
| parameters | JSON | 参数规范 (JSON Schema) | NOT NULL |
| enabled | BOOLEAN | 是否启用 | DEFAULT TRUE |

**File Format** (TOOLS.md):
```markdown
# 工具定义

## 文件操作
- read_file: 读取文件内容
- write_file: 写入文件内容

## 网络操作
- search_web: 搜索互联网
- fetch_url: 获取网页内容

## 代码操作
- execute_code: 执行代码片段
```

---

## Database Schema

### SQLite Tables

```sql
-- 记忆条目表
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('conversation', 'decision', 'summary', 'manual')),
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT
);

-- 向量索引表 (sqlite-vss)
CREATE VIRTUAL TABLE memory_embeddings USING vss0(
    embedding(384)
);

-- 人格配置缓存表
CREATE TABLE spirit_cache (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    role TEXT NOT NULL,
    personality TEXT NOT NULL,
    values TEXT NOT NULL,
    behavior_rules TEXT NOT NULL,
    file_path TEXT UNIQUE,
    last_modified TEXT NOT NULL
);

-- 用户画像缓存表
CREATE TABLE owner_cache (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    name TEXT NOT NULL,
    age INTEGER,
    occupation TEXT,
    interests TEXT NOT NULL DEFAULT '[]',
    goals TEXT NOT NULL DEFAULT '[]',
    preferences TEXT NOT NULL DEFAULT '{}',
    file_path TEXT UNIQUE,
    last_modified TEXT NOT NULL
);

-- 每日日志索引表
CREATE TABLE daily_logs (
    date TEXT PRIMARY KEY,
    file_path TEXT UNIQUE,
    entries TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    created_at TEXT NOT NULL
);

-- 工具定义缓存表
CREATE TABLE tool_definitions (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    parameters TEXT NOT NULL,
    enabled INTEGER DEFAULT 1
);
```

---

## Indexes

```sql
-- 记忆条目索引
CREATE INDEX idx_memory_entries_created_at ON memory_entries(created_at);
CREATE INDEX idx_memory_entries_content_type ON memory_entries(content_type);
CREATE INDEX idx_memory_entries_source_file ON memory_entries(source_file);

-- 每日日志索引
CREATE INDEX idx_daily_logs_date ON daily_logs(date);
```

---

## Relationships

| 关系 | 类型 | 说明 |
|------|------|------|
| MemoryEntry → DailyLog | N:1 | 多个条目属于一个日志 |
| MemoryEntry → VectorStore | 1:1 | 每个条目有一个向量 |
| SpiritConfig → ContextBuilder | 1:1 | 人格配置作为上下文一部分 |
| OwnerProfile → ContextBuilder | 1:1 | 用户画像作为上下文一部分 |
| ToolDefinition → ContextBuilder | N:1 | 工具定义作为上下文一部分 |
