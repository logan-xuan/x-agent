# Contract: Runtime 压缩 Profile 与配置映射

**Feature Branch**: `003-runtime-compression-redesign`  
**Date**: 2026-04-08

## 1. 目标

本契约定义 runtime 压缩 profile 从配置模型到运行时实例的映射规则，确保压缩算法重构不会破坏现有配置入口。

## 2. 配置来源

### Pydantic 配置模型

- `RuntimeCompressionProfileConfig`
- `RuntimeCompressionPressureConfig`
- `RuntimeCompressionPersistConfig`
- `RuntimeCompressionPruningConfig`
- `RuntimeCompressionMicrocompactConfig`
- `RuntimeCompressionCollapseConfig`
- `RuntimeCompressionAutocompactConfig`
- `RuntimeCompressionMemoryFlushConfig`
- `RuntimeCompressionQualityConfig`

### 运行时转换入口

```python
_to_compression_profile(profile: RuntimeCompressionProfileConfig) -> CompressionProfile
CompressionProfileProvider.get(name: str) -> CompressionProfile
```

## 3. 映射约束

### 3.1 必须保留的维度

以下配置维度必须继续可配置：

- `pressure`
- `persist`
- `pruning`
- `microcompact`
- `collapse`
- `autocompact`
- `memory_flush`
- `quality`
- `retain_recent_messages`

### 3.2 校验约束

配置加载时必须继续校验：

- `single_result_chars <= aggregate_result_chars`
- `0 < max_history_share < 1`
- `yellow_pct < orange_pct < red_pct < hard_stop_pct < 1`
- `min_compression_gain_tokens >= 0`

### 3.3 默认 profile 约束

- 必须保留命名 profile 选择能力
- `runtime.defaults.compression_profile` 必须指向已存在的 profile
- `CompressionProfileProvider` 必须返回 defensive copy，避免调用方污染共享配置

## 4. 算法重构对配置的影响规则

### 允许

- 在不破坏已有字段含义的前提下重解释阶段决策逻辑
- 增加内部派生状态，如 `CompressionBudgetState`、阶段决策对象
- 在已有配置模型无法表达目标时增量新增字段

### 不允许

- 直接移除现有 profile 子结构
- 让现有配置字段失效但不报错
- 把关键阈值硬编码回 pipeline，绕过配置系统

## 5. 兼容性要求

### 5.1 对调用方

以下调用方不应因 profile 重构被迫改写调用方式：

- `runtime/service.py`
- `AgentBridge`
- `CompressionProfileProvider`
- 现有 profile provider 单元测试

### 5.2 对配置文件

在没有新增字段的情况下：

- 现有 `runtime.compression_profiles.*` 配置必须继续有效
- 默认 profile 名称应保持可用
- 非法配置必须在启动或加载期失败，而不是运行时静默退化
