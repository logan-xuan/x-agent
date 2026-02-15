# Data Model: Agent 核心主引导流程

**Feature**: Agent 核心主引导流程  
**Date**: 2026-02-15

---

## 1. 实体定义

### 1.1 AgentContext (Agent 上下文)

聚合根，包含 Agent 执行所需的全部上下文信息。

```python
class AgentContext(BaseModel):
    """Agent 执行上下文"""
    
    # 标识
    session_id: str                    # 会话唯一标识
    session_type: SessionType          # 会话类型：MAIN / SHARED
    created_at: datetime               # 上下文创建时间
    
    # 文件内容
    agents_content: Optional[str]      # AGENTS.md 原始内容
    spirit_content: Optional[str]      # SPIRIT.md 原始内容
    owner_content: Optional[str]       # OWNER.md 原始内容
    memory_content: Optional[str]      # MEMORY.md 原始内容（主会话 only）
    tools_content: Optional[str]       # TOOLS.md 原始内容
    daily_memories: List[str]          # 今日 + 昨日 memory 文件内容
    
    # 元数据
    loaded_files: List[str]            # 已加载的文件列表
    load_time_ms: int                  # 加载耗时（毫秒）
    version: str                       # 上下文版本（用于缓存）
```

### 1.2 SessionType (会话类型)

枚举类型，区分主会话和共享上下文。

```python
class SessionType(str, Enum):
    """会话类型"""
    MAIN = "main"          # 主会话：单用户对话，可加载 MEMORY.md
    SHARED = "shared"      # 共享上下文：群聊/多用户，禁止加载 MEMORY.md
```

### 1.3 FileLoadResult (文件加载结果)

文件加载操作的统一返回结构。

```python
class FileLoadResult(BaseModel):
    """文件加载结果"""
    
    file_path: str                     # 文件路径
    success: bool                      # 是否成功
    content: Optional[str]             # 文件内容（成功时）
    error: Optional[str]               # 错误信息（失败时）
    loaded_at: datetime                # 加载时间
    from_cache: bool                   # 是否来自缓存
    is_default: bool                   # 是否使用默认模板创建
```

### 1.4 ContextFile (上下文文件)

上下文文件的元数据定义。

```python
class ContextFile(BaseModel):
    """上下文文件定义"""
    
    name: str                          # 文件名（如 AGENTS.md）
    path: str                          # 相对路径（如 workspace/AGENTS.md）
    required: bool                     # 是否必需
    main_session_only: bool            # 是否仅在主会话加载
    load_order: int                    # 加载顺序（越小越先加载）
    default_template: Optional[str]    # 默认模板内容（缺失时使用）
```

### 1.5 MemoryEntry (记忆条目)

MEMORY.md 中的单个记忆条目。

```python
class MemoryEntry(BaseModel):
    """记忆条目"""
    
    id: str                            # 唯一标识（UUID）
    content: str                       # 记忆内容
    source_date: Optional[date]        # 来源日期（来自每日笔记）
    importance: int                    # 重要性评分（1-5）
    category: str                      # 分类（如 "经验", "决策", "洞察"）
    created_at: datetime               # 创建时间
    updated_at: datetime               # 更新时间
```

---

## 2. 文件加载顺序

```
加载顺序 (load_order):
┌──────────────────────────────────────────────────────┐
│  1. AGENTS.md      (required=True,  main_only=False) │
│  2. SPIRIT.md      (required=True,  main_only=False) │
│  3. OWNER.md       (required=True,  main_only=False) │
│  4. TOOLS.md       (required=False, main_only=False) │
│  5. memory/YYYY-MM-DD.md (今日)                      │
│  6. memory/YYYY-MM-DD.md (昨日)                      │
│  7. MEMORY.md      (required=False, main_only=True)  │
└──────────────────────────────────────────────────────┘
```

---

## 3. 状态转换

### 3.1 上下文生命周期

```
┌──────────┐    会话开始    ┌──────────┐   加载完成   ┌──────────┐
│  INITIAL │ ─────────────► │ LOADING  │ ───────────► │  READY   │
└──────────┘                └──────────┘              └────┬─────┘
                                                           │
                              文件变更 / 用户提问         │
                              ┌────────────────────────────┘
                              ▼
                         ┌──────────┐   重载完成   ┌──────────┐
                         │ RELOADING│ ───────────► │  READY   │
                         └──────────┘              └──────────┘
```

### 3.2 文件加载状态

```
┌──────────┐   文件存在    ┌──────────┐   读取成功   ┌──────────┐
│  CHECK   │ ───────────► │  READ    │ ───────────► │  SUCCESS │
└────┬─────┘              └────┬─────┘              └──────────┘
     │ 文件缺失                │ 读取失败
     ▼                         ▼
┌──────────┐              ┌──────────┐
│  CREATE  │              │  FALLBACK│
│(default) │              │(cache)   │
└────┬─────┘              └────┬─────┘
     │                         │
     └──────────┬──────────────┘
                ▼
           ┌──────────┐
           │  SUCCESS │
           │(with note)│
           └──────────┘
```

---

## 4. 验证规则

### 4.1 AgentContext 验证

```python
@validator('memory_content')
def validate_memory_in_main_only(cls, v, values):
    """MEMORY.md 仅在主会话中允许有内容"""
    session_type = values.get('session_type')
    if session_type == SessionType.SHARED and v is not None:
        raise ValueError("MEMORY.md 不能在共享上下文中加载")
    return v

@validator('daily_memories')
def validate_daily_memory_count(cls, v):
    """每日笔记最多加载 2 天（今日 + 昨日）"""
    if len(v) > 2:
        raise ValueError("每日笔记最多加载 2 天")
    return v
```

### 4.2 文件路径验证

```python
@validator('path')
def validate_path_in_workspace(cls, v):
    """文件路径必须在 workspace 目录内"""
    resolved = Path(v).resolve()
    workspace = Path("workspace").resolve()
    if not str(resolved).startswith(str(workspace)):
        raise ValueError(f"文件路径 {v} 必须在 workspace 目录内")
    return v
```

---

## 5. 关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentContext                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ SessionType │  │  文件内容   │  │   元数据    │             │
│  │  (enum)     │  │  (strings)  │  │  (stats)    │             │
│  └──────┬──────┘  └─────────────┘  └─────────────┘             │
│         │                                                       │
│         │ 1:N                                                   │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────┐               │
│  │           ContextFile (配置)                 │               │
│  │  - name, path, required                       │               │
│  │  - main_session_only, load_order              │               │
│  │  - default_template                           │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  ┌─────────────────────────────────────────────┐               │
│  │         FileLoadResult (操作结果)            │               │
│  │  - success, content, error                   │               │
│  │  - from_cache, is_default                    │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  ┌─────────────────────────────────────────────┐               │
│  │         MemoryEntry (记忆条目)               │               │
│  │  - id, content, importance                   │               │
│  │  - category, source_date                     │               │
│  └─────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 存储格式

### 6.1 文件系统布局

```
workspace/
├── AGENTS.md              # 主引导文件（必需）
├── SPIRIT.md              # 身份定义（必需）
├── OWNER.md               # 用户信息（必需）
├── MEMORY.md              # 长期记忆（可选，主会话 only）
├── TOOLS.md               # 工具配置（可选）
├── BOOTSTRAP.md           # 首次启动引导（一次性）
└── memory/                # 每日笔记目录
    ├── 2026-02-14.md
    ├── 2026-02-15.md
    └── ...
```

### 6.2 MEMORY.md 结构建议

```markdown
# MEMORY.md - 长期记忆

## 重要决策
- [2026-02-15] 决定使用文件系统存储上下文
- [2026-02-14] 确定主会话与共享上下文的判定机制

## 经验教训
- 异步 I/O 对性能至关重要
- 文件锁可防止并发冲突

## 用户偏好
- 喜欢简洁的回复风格
- 偏好中文交流
```

### 6.3 memory/YYYY-MM-DD.md 结构

```markdown
# 2026-02-15

## 今日事件
- 完成了 Agent 引导流程的规范设计
- 确定了技术选型方案

## 重要洞察
- 保持简单是最好的设计原则

## 待办事项
- [ ] 实现文件监控模块
- [ ] 编写单元测试
```
