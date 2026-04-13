# x-agent 开发指南

自动根据 feature plan 更新。最近更新时间：2026-04-08

## 当前技术栈

- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy
- runtime/context
- runtime/turn
- gateway/agent_bridge
- pytest
- pytest-asyncio

## 当前项目结构

```text
backend/
├── src/
│   ├── config/
│   ├── gateway/
│   ├── runtime/
│   └── services/
├── tests/
│   └── unit/
└── pyproject.toml

specs/
└── 003-runtime-compression-redesign/
```

## 常用命令

```bash
cd backend
pytest --no-cov tests/unit/test_runtime_compression_pipeline.py -q
pytest --no-cov tests/unit/test_runtime_compression_verifier.py -q
pytest --no-cov tests/unit/test_runtime_gateway_adapter.py -q
pytest --no-cov tests/unit/test_runtime_turn_controller.py -q
pytest --no-cov tests/unit/test_runtime_compression_profiles.py -q
ruff check src
```

## 代码风格

- Python 代码保持完整类型注解
- 优先拆分复杂逻辑，避免把预算决策、语义裁剪和 bridge 透传继续堆进单个函数
- 新增注释、文档字符串和规划文档统一使用中文

## 最近变更

- `003-runtime-compression-redesign`：新增 runtime 压缩算法重构规划，覆盖预算驱动阶段决策、唯一 collapse 快照、verifier/rollback 契约、bridge/controller 压缩闭环与 profile 配置映射

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
