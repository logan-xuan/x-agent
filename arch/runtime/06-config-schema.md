# Runtime Config Schema 详细方案

> 范围：runtime 配置模型、Pydantic schema 设计、默认 profile、以及与现有 `backend/src/config/models.py` 的兼容迁移方案。

---

## 1. 目标

新 runtime 需要一套配置模型来统一表达：

- 单任务回合预算
- 压缩策略
- session 生命周期与 lane
- subagent / child session 约束
- tool policy 的 runtime 部分

重点不是替换现有所有配置，而是：

1. 在现有 `config.models` 基础上新增一个清晰的 `runtime` 配置树
2. 提供向后兼容的迁移映射

---

## 2. 现有配置基线

当前已有配置模型位于：

- `backend/src/config/models.py`

现有相关部分：

- `CompressionConfig`
- `PlanConfig`
- `ToolsConfig`
- `WorkspaceConfig`
- `LoggingConfig`

问题：

- 回合预算、压缩预算、session 编排配置还分散
- 很多参数是“单点参数”，没有 profile 概念
- 无法很好表达主 agent 与 child agent 的差异化限制

补充约束：

- `config.models` 虽然已支持 primary / backup provider，但备用 provider onboarding 不能只改 `model_id`
- 同一份 key 在不同 `base_url` / endpoint 上未必可用
- 进入生产配置前，应先通过 `/api/v1/dev/llm-stream-probe` 验证候选 `base_url + model_id + key` 组合

---

## 3. 新配置树

建议在现有总配置里新增：

```yaml
runtime:
  defaults:
    turn_profile: default
    compression_profile: balanced
    session_profile: default
  turn_profiles:
    default: ...
    child-default: ...
  compression_profiles:
    balanced: ...
    aggressive: ...
    conservative: ...
  session_profiles:
    default: ...
    child-default: ...
  tools:
    defaults: ...
    by_name: ...
```

---

## 4. Pydantic 模型设计

### 4.1 TurnBudgetProfileModel

```python
from pydantic import BaseModel, Field


class TurnBudgetProfileModel(BaseModel):
    max_turns: int = Field(default=12, ge=1, le=100)
    max_wall_time_ms: int = Field(default=180000, ge=1000, le=3600000)
    max_total_tokens: int = Field(default=120000, ge=1000)
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    max_tool_calls: int = Field(default=24, ge=1, le=500)
    max_parallel_tools: int = Field(default=4, ge=1, le=32)
    max_spawns: int = Field(default=3, ge=0, le=32)
    compact_trigger_tokens: int = Field(default=80000, ge=1000)
    collapse_trigger_tokens: int = Field(default=60000, ge=1000)
    tool_result_single_chars: int = Field(default=50000, ge=1000)
    tool_result_per_message_chars: int = Field(default=200000, ge=1000)
```

### 4.2 CompressionProfileModel

```python
class CompressionPressureModel(BaseModel):
    yellow_pct: float = Field(default=0.50, gt=0.0, lt=1.0)
    orange_pct: float = Field(default=0.68, gt=0.0, lt=1.0)
    red_pct: float = Field(default=0.82, gt=0.0, lt=1.0)
    hard_stop_pct: float = Field(default=0.90, gt=0.0, lt=1.0)


class CompressionPersistModel(BaseModel):
    single_result_chars: int = Field(default=50000, ge=1000)
    aggregate_result_chars: int = Field(default=200000, ge=1000)
    artifact_preview_chars: int = Field(default=2000, ge=200)
    artifact_preview_head_chars: int = Field(default=900, ge=50)
    artifact_preview_tail_chars: int = Field(default=700, ge=50)


class CompressionPruningModel(BaseModel):
    enabled: bool = True
    ttl_ms: int = Field(default=300000, ge=1000)
    preserve_recent_assistants: int = Field(default=3, ge=1, le=20)
    min_prunable_tool_chars: int = Field(default=50000, ge=1000)
    soft_trim_max_chars: int = Field(default=4000, ge=100)
    soft_trim_head_chars: int = Field(default=1500, ge=0)
    soft_trim_tail_chars: int = Field(default=1500, ge=0)
    hard_clear_enabled: bool = True
    hard_clear_placeholder: str = "[Old tool result content cleared]"


class CompressionMicrocompactModel(BaseModel):
    enabled: bool = True
    trigger_pct: float = Field(default=0.50, gt=0.0, lt=1.0)
    max_units_per_pass: int = Field(default=8, ge=1, le=100)
    preserve_error_results: bool = True


class CompressionCollapseModel(BaseModel):
    enabled: bool = True
    trigger_pct: float = Field(default=0.68, gt=0.0, lt=1.0)
    max_segment_tokens: int = Field(default=12000, ge=100)
    min_segment_turns: int = Field(default=2, ge=1, le=50)


class CompressionAutocompactModel(BaseModel):
    enabled: bool = True
    trigger_pct: float = Field(default=0.82, gt=0.0, lt=1.0)
    reserve_tokens_floor: int = Field(default=20000, ge=0)
    max_history_share: float = Field(default=0.50, gt=0.0, lt=1.0)
    fallback_summary_max_chars: int = Field(default=8000, ge=500)


class CompressionMemoryFlushModel(BaseModel):
    enabled: bool = True
    soft_threshold_tokens: int = Field(default=4000, ge=0)


class CompressionQualityModel(BaseModel):
    min_compression_gain_tokens: int = Field(default=1000, ge=0)
    require_post_check: bool = True
    rollback_on_invariant_failure: bool = True


class CompressionProfileModel(BaseModel):
    mode: str = Field(default="balanced")
    pressure: CompressionPressureModel = Field(default_factory=CompressionPressureModel)
    persist: CompressionPersistModel = Field(default_factory=CompressionPersistModel)
    pruning: CompressionPruningModel = Field(default_factory=CompressionPruningModel)
    microcompact: CompressionMicrocompactModel = Field(default_factory=CompressionMicrocompactModel)
    collapse: CompressionCollapseModel = Field(default_factory=CompressionCollapseModel)
    autocompact: CompressionAutocompactModel = Field(default_factory=CompressionAutocompactModel)
    memory_flush: CompressionMemoryFlushModel = Field(default_factory=CompressionMemoryFlushModel)
    quality: CompressionQualityModel = Field(default_factory=CompressionQualityModel)
```

### 4.3 SessionProfileModel

```python
class SessionLaneLimitsModel(BaseModel):
    main: int = Field(default=1, ge=1, le=32)
    followup: int = Field(default=2, ge=1, le=32)
    subagent: int = Field(default=4, ge=1, le=64)
    cron: int = Field(default=2, ge=1, le=32)
    background_tool: int = Field(default=2, ge=1, le=32)


class SessionProfileModel(BaseModel):
    idle_archive_ms: int = Field(default=86400000, ge=60000)
    child_auto_archive_ms: int = Field(default=3600000, ge=60000)
    allow_child_sessions: bool = True
    child_prompt_mode: str = Field(default="minimal")
    child_max_depth: int = Field(default=1, ge=0, le=3)
    child_default_budget_profile: str = Field(default="child-default")
    lane_limits: SessionLaneLimitsModel = Field(default_factory=SessionLaneLimitsModel)
```

### 4.4 RuntimeToolPolicyModel

```python
class RuntimeToolPolicyModel(BaseModel):
    max_result_size_chars: int = Field(default=50000, ge=100)
    max_uses_per_turn: int = Field(default=8, ge=1, le=100)
    max_uses_per_session: int = Field(default=50, ge=1, le=1000)
    max_parallelism: int = Field(default=2, ge=1, le=32)
    default_timeout_ms: int = Field(default=30000, ge=100, le=3600000)
    compactable: bool = True
    persist_large_output: bool = True
    allow_in_subagent: bool = True
    cost_weight: int = Field(default=1, ge=1, le=100)
    repeat_signature_limit: int = Field(default=2, ge=1, le=20)
```

### 4.5 RuntimeConfigModel

```python
class RuntimeDefaultsModel(BaseModel):
    turn_profile: str = "default"
    compression_profile: str = "balanced"
    session_profile: str = "default"


class RuntimeToolsModel(BaseModel):
    defaults: RuntimeToolPolicyModel = Field(default_factory=RuntimeToolPolicyModel)
    by_name: dict[str, RuntimeToolPolicyModel] = Field(default_factory=dict)


class RuntimeConfigModel(BaseModel):
    defaults: RuntimeDefaultsModel = Field(default_factory=RuntimeDefaultsModel)
    turn_profiles: dict[str, TurnBudgetProfileModel] = Field(default_factory=dict)
    compression_profiles: dict[str, CompressionProfileModel] = Field(default_factory=dict)
    session_profiles: dict[str, SessionProfileModel] = Field(default_factory=dict)
    tools: RuntimeToolsModel = Field(default_factory=RuntimeToolsModel)
```

---

## 5. 推荐默认值

### 5.1 主 agent

```yaml
runtime:
  defaults:
    turn_profile: default
    compression_profile: balanced
    session_profile: default
  turn_profiles:
    default:
      max_turns: 12
      max_wall_time_ms: 180000
      max_total_tokens: 120000
      max_tool_calls: 24
      max_parallel_tools: 4
      max_spawns: 3
      tool_result_single_chars: 50000
      tool_result_per_message_chars: 200000
```

### 5.2 child agent

```yaml
runtime:
  turn_profiles:
    child-default:
      max_turns: 6
      max_wall_time_ms: 90000
      max_total_tokens: 60000
      max_tool_calls: 12
      max_parallel_tools: 3
      max_spawns: 0
      tool_result_single_chars: 30000
      tool_result_per_message_chars: 100000
```

### 5.3 balanced compression

```yaml
runtime:
  compression_profiles:
    balanced:
      mode: balanced
      pressure:
        yellow_pct: 0.50
        orange_pct: 0.68
        red_pct: 0.82
        hard_stop_pct: 0.90
```

---

## 6. 配置文件示例

完整示例：

```yaml
runtime:
  defaults:
    turn_profile: default
    compression_profile: balanced
    session_profile: default

  turn_profiles:
    default:
      max_turns: 12
      max_wall_time_ms: 180000
      max_total_tokens: 120000
      max_tool_calls: 24
      max_parallel_tools: 4
      max_spawns: 3
      tool_result_single_chars: 50000
      tool_result_per_message_chars: 200000
    child-default:
      max_turns: 6
      max_wall_time_ms: 90000
      max_total_tokens: 60000
      max_tool_calls: 12
      max_parallel_tools: 3
      max_spawns: 0
      tool_result_single_chars: 30000
      tool_result_per_message_chars: 100000

  compression_profiles:
    balanced:
      mode: balanced
      pressure:
        yellow_pct: 0.50
        orange_pct: 0.68
        red_pct: 0.82
        hard_stop_pct: 0.90

  session_profiles:
    default:
      idle_archive_ms: 86400000
      child_auto_archive_ms: 3600000
      allow_child_sessions: true
      child_prompt_mode: minimal
      child_max_depth: 1
      child_default_budget_profile: child-default
      lane_limits:
        main: 1
        followup: 2
        subagent: 4
        cron: 2
        background_tool: 2

  tools:
    defaults:
      max_result_size_chars: 50000
      max_uses_per_turn: 8
      max_uses_per_session: 50
      max_parallelism: 2
      default_timeout_ms: 30000
      compactable: true
      persist_large_output: true
      allow_in_subagent: true
      cost_weight: 1
      repeat_signature_limit: 2
    by_name:
      web_search:
        max_result_size_chars: 30000
        max_uses_per_turn: 8
        max_uses_per_session: 30
        max_parallelism: 2
        default_timeout_ms: 20000
        compactable: true
        persist_large_output: true
        allow_in_subagent: true
        cost_weight: 2
        repeat_signature_limit: 2
```

---

## 7. 与现有配置的兼容映射

### 7.1 现有字段 -> 新字段

建议在迁移期做以下映射：

| 现有字段 | 新字段 |
|---|---|
| `compression.threshold_tokens` | `runtime.turn_profiles.default.compact_trigger_tokens` |
| `compression.retention_count` | `runtime.compression_profiles.balanced.pruning.preserve_recent_assistants` |
| `plan.max_replan_count` | `runtime.turn_profiles.default.max_turns` 的辅助策略，不直接一比一映射 |
| `tools.terminal_timeout` | `runtime.tools.by_name.terminal.default_timeout_ms` |
| `tools.terminal_max_output` | `runtime.tools.by_name.terminal.max_result_size_chars` |

### 7.2 迁移原则

- 旧字段继续保留一段时间
- 新字段优先级高于旧字段
- 加一层 `RuntimeConfigProvider`，避免业务逻辑直接感知新旧差异

---

## 8. 推荐实现方式

### 8.1 在现有 `config/models.py` 中新增

建议新增：

- `RuntimeConfigModel`
- `RuntimeDefaultsModel`
- `TurnBudgetProfileModel`
- `CompressionProfileModel`
- `SessionProfileModel`
- `RuntimeToolPolicyModel`

### 8.2 在 `config/loader.py` 中接入

目标：

- 启动时统一加载 `runtime`
- 提供默认 profile 补全
- 在缺失时自动注入默认值

### 8.3 在 `config/validator.py` 中接入

需要额外验证：

- `yellow_pct < orange_pct < red_pct < hard_stop_pct`
- 默认 profile 引用必须存在
- child profile 必须存在可用的 `child_default_budget_profile`

---

## 9. RuntimeConfigProvider

不要让业务代码直接依赖巨大的 Pydantic 对象。

建议增加：

```python
class RuntimeConfigProvider:
    def __init__(self, config: RuntimeConfigModel): ...

    def get_turn_profile(self, name: str) -> TurnBudgetProfileModel: ...
    def get_compression_profile(self, name: str) -> CompressionProfileModel: ...
    def get_session_profile(self, name: str) -> SessionProfileModel: ...
    def get_tool_policy(self, tool_name: str) -> RuntimeToolPolicyModel: ...
```

这样：

- `TurnController` 不直接依赖原始 config tree
- `CompressionPipeline` 不直接依赖 YAML 结构
- `SessionOrchestrator` 能稳定获取 session profile

---

## 10. 分阶段接入顺序

### Phase 1

先接 `TurnBudgetProfileModel` 与 `RuntimeToolPolicyModel`，为 `TurnController` 服务。

### Phase 2

再接 `CompressionProfileModel`，为 `CompressionPipeline` 服务。

### Phase 3

最后接 `SessionProfileModel`，为 `SessionOrchestrator` 与 child session 服务。

---

## 11. 验收标准

配置层完成后，应满足：

- runtime 有独立配置树
- 支持 profile 化，不是零散参数
- 有新旧配置兼容映射
- 业务代码通过 provider 读取配置
- 主 agent 与 child agent 能读取不同 profile

如果这一层不先定好，后续 runtime 实现会继续把预算、压缩、session 参数散落在各个模块里。
