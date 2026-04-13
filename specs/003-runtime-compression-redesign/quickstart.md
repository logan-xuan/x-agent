# Quickstart: Runtime 压缩算法重构

**Feature Branch**: `003-runtime-compression-redesign`  
**Date**: 2026-04-08

## 1. 目标

本 quickstart 用于指导实现和验证 runtime 压缩重构，确保预算驱动、语义护栏、bridge 闭环和配置映射都能被逐步验证。

## 2. 实现前准备

在仓库根目录执行：

```bash
cd /Users/xuan.lx/Documents/x-agent
```

先阅读以下文档：

1. `docs/plans/runtime-compression-redesign-design.md`
2. `docs/architecture-review/06-runtime-orchestration.md`
3. `specs/003-runtime-compression-redesign/spec.md`
4. `specs/003-runtime-compression-redesign/research.md`

## 3. 基线验证

在修改代码前，先运行与本特性直接相关的测试套件，记录当前基线：

```bash
pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q
pytest --no-cov backend/tests/unit/test_runtime_compression_verifier.py -q
pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -q
pytest --no-cov backend/tests/unit/test_runtime_turn_controller.py -q
pytest --no-cov backend/tests/unit/test_runtime_compression_profiles.py -q
```

## 4. 推荐实现顺序

### 第一步：收敛阶段决策与预算状态

优先修改：

- `backend/src/runtime/context/compression_pipeline.py`

目标：

- 把阶段选择改成预算驱动
- 保持 `CompressionResult` 兼容
- 让 `budget_state` 成为稳定结果元数据

验证：

```bash
pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q
```

### 第二步：收敛 collapse 与 verifier 语义护栏

优先修改：

- `backend/src/runtime/context/compression_pipeline.py`
- `backend/src/runtime/context/compression_verifier.py`

目标：

- 让 collapse 形成唯一状态快照
- 强化 objective / unresolved / artifact / conclusion / state conflict 校验
- 明确 rollback 与 skip-rollback 语义

验证：

```bash
pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q
pytest --no-cov backend/tests/unit/test_runtime_compression_verifier.py -q
```

### 第三步：打通 bridge 与 controller 压缩闭环

优先修改：

- `backend/src/gateway/agent_bridge.py`
- 必要时补 `backend/src/runtime/turn/controller.py`

目标：

- `_runtime_prepare_model_input()` 和 `_runtime_controller_compact()` 使用一致的压缩结果契约
- 保证 `budget_state`、`verifier_result`、`rollback_*` 元数据不丢失

验证：

```bash
pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -q
pytest --no-cov backend/tests/unit/test_runtime_turn_controller.py -q
```

### 第四步：确认配置映射与 profile 约束

优先修改：

- `backend/src/config/models.py`
- `backend/src/runtime/context/profile_provider.py`
- `backend/src/runtime/service.py`

目标：

- 保持 profile 配置兼容
- 只在确有必要时增量扩展字段
- 加载期继续阻止非法组合

验证：

```bash
pytest --no-cov backend/tests/unit/test_runtime_compression_profiles.py -q
```

## 5. 回归验证

当以上步骤完成后，运行完整的压缩相关回归：

```bash
pytest --no-cov \
  backend/tests/unit/test_runtime_compression_pipeline.py \
  backend/tests/unit/test_runtime_compression_verifier.py \
  backend/tests/unit/test_runtime_gateway_adapter.py \
  backend/tests/unit/test_runtime_turn_controller.py \
  backend/tests/unit/test_runtime_compression_profiles.py -q
```

### 5.1 最新验证记录（2026-04-08）

本次实现核对使用如下结果作为验收基线：

```bash
pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q
# 29 passed

pytest --no-cov backend/tests/unit/test_runtime_compression_verifier.py -q
# 10 passed

pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -q
# 33 passed

pytest --no-cov backend/tests/unit/test_runtime_turn_controller.py -q
# 7 passed

pytest --no-cov backend/tests/unit/test_runtime_compression_profiles.py -q
# 4 passed

pytest --no-cov \
  backend/tests/unit/test_runtime_compression_pipeline.py \
  backend/tests/unit/test_runtime_compression_verifier.py \
  backend/tests/unit/test_runtime_gateway_adapter.py \
  backend/tests/unit/test_runtime_turn_controller.py \
  backend/tests/unit/test_runtime_compression_profiles.py -q
# 83 passed
```

## 6. 完成判定

满足以下条件后，可判定 runtime 压缩重构已经完成并可继续后续集成：

1. pipeline、verifier、bridge、controller、profile provider 的压缩契约测试全部通过。
2. 文档中定义的 `budget_state`、`rollback`、`verifier_result` 元数据能在 bridge 路径上被观察到。
3. `collapse` 不再形成摘要叠加污染。
4. 本轮改动未触碰 legacy compression manager 的行为边界。
5. 聚焦回归矩阵在一次完整运行中达到 `83 passed`。
