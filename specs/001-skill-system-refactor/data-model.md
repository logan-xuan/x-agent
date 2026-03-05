# Data Model: Skill 系统重构

**Feature Branch**: `001-skill-system-refactor`  
**Date**: 2026-03-01  
**Status**: Draft

## 实体概览

```
┌─────────────────────────────────────────────────────────────┐
│                      实体关系图                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  SkillManifest ──────────────────────┐                      │
│       │                               │                      │
│       │ 1:1                           │                      │
│       ▼                               │                      │
│  SkillCapabilityVector               │                      │
│       │                               │                      │
│       │                               │                      │
│       └─────────► SkillCard ◄────────┘                      │
│                      │                                       │
│                      │                                       │
│                      ▼                                       │
│             SkillSearchContext                              │
│                      │                                       │
│                      │                                       │
│                      ▼                                       │
│            SkillExecutionContext                            │
│                      │                                       │
│                      │                                       │
│                      ▼                                       │
│            SkillExecutionResult                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心实体

### 1. SkillManifest（技能清单）

技能的完整定义描述，是系统的核心数据模型。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| **Identity** | | | |
| skill_id | str | ✅ | 唯一标识 (kebab-case) |
| name | str | ✅ | 显示名称 |
| version | str | ✅ | 语义版本 (semver) |
| vendor | str | | 供应商/作者 |
| signature | str | | 数字签名 |
| **Capability** | | | |
| description | str | ✅ | 简短描述（一句话） |
| description_detail | str | | 详细描述 |
| tags | list[str] | | 标签列表 |
| domains | list[str] | | 领域: document, web, data |
| examples | list[str] | | 使用示例 |
| **IO Contract** | | | |
| input_schema | dict | | JSON Schema |
| output_schema | dict | | JSON Schema |
| error_schema | dict | | 错误格式 |
| **Execution** | | | |
| endpoint | str | | 调用端点/入口 |
| callable | str | | 可调用对象路径 |
| timeout_ms | int | | 超时时间 (default: 30000) |
| max_retries | int | | 最大重试次数 (default: 3) |
| idempotency | bool | | 是否幂等 (default: False) |
| **Constraints** | | | |
| preconditions | list[str] | | 前置条件 |
| postconditions | list[str] | | 后置条件 |
| invariants | list[str] | | 不变式 |
| os | list[str] | | OS 限制 |
| requires_bins | list[str] | | 必需的二进制 |
| requires_env | list[str] | | 必需的环境变量 |
| requires_config | list[str] | | 必需的配置 |
| **Risk & Policy** | | | |
| risk_level | RiskLevel | | 风险等级 (default: LOW) |
| data_access | DataAccessLevel | | 数据访问级别 |
| side_effect | bool | | 是否有副作用 |
| required_auth | list[str] | | 所需权限 |
| approval_mode | ApprovalMode | | 审批模式 (default: AUTO) |
| always | bool | | 始终加载 |
| auto_trigger | bool | | 允许自动触发 (default: True) |
| user_invocable | bool | | 用户可调用 (default: True) |
| **Observability** | | | |
| telemetry | bool | | 启用遥测 (default: True) |
| trace_fields | list[str] | | 追踪字段 |
| redaction_rules | list[str] | | 脱敏规则 |
| **Progressive** | | | |
| stages | list[ExecutionStage] | | 执行阶段 |
| supports_dry_run | bool | | 支持预演 |
| supports_rollback | bool | | 支持回滚 |
| **Structure** | | | |
| path | Path | | 技能目录路径 |
| has_scripts | bool | | 有 scripts/ 目录 |
| has_references | bool | | 有 references/ 目录 |
| has_assets | bool | | 有 assets/ 目录 |
| **Display** | | | |
| emoji | str | | 展示图标 |
| homepage | str | | 主页链接 |

---

### 2. SkillSource（技能来源）

枚举类型，标识技能的注册来源。

| 值 | 优先级 | 说明 |
|-----|-------|------|
| USER | 100 (最高) | 用户/工作空间级 |
| SYSTEM | 200 | 系统内置 |
| REMOTE | 300 (最低) | 远程仓库（本期不实现） |

---

### 3. RiskLevel（风险等级）

枚举类型，标识技能的风险级别。

| 值 | 说明 |
|-----|------|
| LOW | 低风险：只读、无副作用 |
| MEDIUM | 中风险：修改文件、创建内容 |
| HIGH | 高风险：删除、发送请求、执行代码 |
| CRITICAL | 关键：系统操作、安全相关 |

---

### 4. DataAccessLevel（数据访问级别）

枚举类型，标识技能的数据访问权限。

| 值 | 说明 |
|-----|------|
| READ_ONLY | 只读 |
| READ_WRITE | 读写 |
| CREATE | 创建 |
| DELETE | 删除 |
| EXECUTE | 执行代码 |

---

### 5. ApprovalMode（审批模式）

枚举类型，标识技能的审批要求。

| 值 | 说明 |
|-----|------|
| AUTO | 自动执行 |
| CONFIRM | 需要用户确认 |
| APPROVAL | 需要审批流程 |
| MANUAL | 仅手动触发 |

---

### 6. ExecutionStage（执行阶段）

枚举类型，标识渐进式执行的阶段。

| 值 | 说明 |
|-----|------|
| DRY_RUN | 预演（模拟执行） |
| PLAN | 规划（生成计划） |
| CONFIRM | 确认（等待用户） |
| COMMIT | 提交（执行操作） |
| ROLLBACK | 回滚（撤销操作） |

---

### 7. SkillCapabilityVector（能力向量）

用于语义检索的能力描述向量。

| 字段 | 类型 | 说明 |
|------|------|------|
| skill_id | str | 技能ID |
| capability_text | str | 能力描述文本（一句话 + 详细描述 + 例子） |
| tool_signature | str | 函数签名文本（用于 LLM tool use） |
| embedding | list[float] | 嵌入向量 (384维) |
| embedding_model | str | 使用的嵌入模型 |
| embedding_updated_at | datetime | 向量更新时间 |
| keywords | list[str] | 关键词列表 |
| domains | list[str] | 领域列表 |

---

### 8. SkillSearchContext（检索上下文）

技能检索的输入上下文。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_input | str | 用户输入 |
| available_params | dict[str, Any] | 已知参数（上下文） |
| user_permissions | list[str] | 用户权限 |
| environment | dict[str, str] | 环境信息 |
| budget | SearchBudget | 预算约束（可选） |

### SearchBudget

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_latency_ms | int | 1000 | 最大延迟 |
| max_cost | float | 0.01 | 最大成本 |

---

### 9. SkillCard（技能卡片）

技能发现的输出格式，提供决策辅助信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| **基本信息** | | |
| skill_id | str | 技能ID |
| name | str | 显示名称 |
| description | str | 描述 |
| emoji | str | 图标 |
| **匹配信息** | | |
| relevance_score | float | 相关性得分 (0-1) |
| match_reason | str | 匹配原因 |
| **风险与策略** | | |
| risk_level | RiskLevel | 风险等级 |
| side_effect | bool | 是否有副作用 |
| approval_mode | ApprovalMode | 审批模式 |
| approval_required | bool | 是否需要审批 |
| **参数信息** | | |
| input_schema | dict | 输入 Schema |
| required_params | list[str] | 必需参数列表 |
| available_params | list[str] | 上下文中已有的参数 |
| missing_params | list[str] | 缺失的参数 |
| schema_fit_score | float | Schema 填充度得分 |
| **执行选项** | | |
| supports_dry_run | bool | 支持预演 |
| supports_rollback | bool | 支持回滚 |
| **估计** | | |
| estimated_latency_ms | int | 预估延迟 |
| estimated_cost | float | 预估成本 |
| **快速参考** | | |
| quick_reference | str | 快速参考 |
| when_to_use | str | 适用场景 |

---

### 10. SkillExecutionContext（执行上下文）

技能执行的运行时上下文。

| 字段 | 类型 | 说明 |
|------|------|------|
| **会话信息** | | |
| session_id | str | 会话ID |
| conversation_id | str | 对话ID |
| **用户信息** | | |
| user_input | str | 用户输入 |
| user_permissions | list[str] | 用户权限 |
| **参数** | | |
| params | dict[str, Any] | 执行参数 |
| missing_params | list[str] | 缺失的参数 |
| **执行阶段** | | |
| stage | ExecutionStage | 当前阶段 |
| dry_run | bool | 预演模式 |
| auto_confirm | bool | 自动确认 |
| **状态** | | |
| state | dict[str, Any] | 状态数据 |
| artifacts | list[dict] | 生成的产物 |
| **追踪** | | |
| trace_id | str | 追踪ID |
| parent_span_id | str | 父 Span ID |

---

### 11. SkillExecutionResult（执行结果）

技能执行的返回结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功 |
| stage | ExecutionStage | 完成的阶段 |
| **输出** | | |
| output | str | 输出内容 |
| data | dict[str, Any] | 结构化数据 |
| artifacts | list[dict] | 生成的产物 |
| **错误** | | |
| error | str | 错误信息 |
| error_code | str | 错误码 |
| recoverable | bool | 是否可恢复 |
| **回滚信息** | | |
| rollback_available | bool | 可否回滚 |
| rollback_data | dict[str, Any] | 回滚数据 |
| **遥测** | | |
| duration_ms | int | 执行耗时 |
| tokens_used | int | Token 消耗 |

---

### 12. SkillScore（评分结果）

混合评分的详细结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| skill_id | str | 技能ID |
| total | float | 综合得分 (0-1) |
| breakdown | dict[str, float] | 各维度得分 |

**breakdown 字段说明**:

| 键 | 权重 | 说明 |
|-----|------|------|
| semantic | 0.35 | 语义相似度 |
| schema_fit | 0.25 | Schema 填充度 |
| policy | 0.20 | 策略得分 |
| latency | 0.10 | 延迟得分 |
| reliability | 0.10 | 可靠性得分 |

---

## 状态转换

### 技能执行状态机

```
              ┌─────────────┐
              │   PENDING   │
              └──────┬──────┘
                     │ start
                     ▼
              ┌─────────────┐
        ┌─────│   DRY_RUN   │─────┐
        │     └──────┬──────┘     │
        │ skip       │ pass       │ fail
        │            ▼            │
        │     ┌─────────────┐     │
        ├─────│    PLAN     │─────┤
        │     └──────┬──────┘     │
        │            │ pass       │
        │            ▼            │
        │     ┌─────────────┐     │
        ├─────│   CONFIRM   │─────┤
        │     └──────┬──────┘     │
        │ skip  ┌────┴────┐       │
        │       │         │       │
        │  confirmed   cancelled  │
        │       │         │       │
        │       ▼         ▼       │
        │ ┌─────────┐ ┌────────┐  │
        └►│ COMMIT  │ │ ABORT  │◄─┘
          └────┬────┘ └────────┘
               │
          ┌────┴────┐
          │         │
       success    fail
          │         │
          ▼         ▼
    ┌──────────┐ ┌──────────┐
    │ SUCCESS  │ │ ROLLBACK │
    └──────────┘ └──────────┘
```

---

## 验证规则

### SkillManifest 验证

1. **skill_id**: 必需，kebab-case，1-64 字符
2. **name**: 必需，1-128 字符
3. **version**: 必需，符合 semver 格式
4. **description**: 必需，1-1024 字符
5. **risk_level**: 必须是有效的 RiskLevel 枚举值
6. **input_schema**: 如果提供，必须是有效的 JSON Schema

### 技能目录结构验证

```
skill/
├── manifest.json     # 必需（或 SKILL.md）
├── SKILL.md          # 可选（人类可读）
├── schemas/          # 可选
├── scripts/          # 可选
├── references/       # 可选
└── assets/           # 可选
```

---

## 索引结构

### 技能向量索引（sqlite-vss）

```sql
CREATE TABLE skill_embeddings (
    skill_id TEXT PRIMARY KEY,
    capability_text TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- 384维 float32
    embedding_model TEXT DEFAULT 'm3e-small',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE skill_embeddings_vss USING vss0(
    embedding(384)
);
```

### 技能注册表缓存

```python
# 内存缓存结构
_cache: dict[str, tuple[SkillManifest, SkillSource]] = {
    "skill_id": (SkillManifest(...), SkillSource.USER),
    ...
}
```
