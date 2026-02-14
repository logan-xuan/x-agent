# Implementation Plan: AI Agent 记忆系统

**Branch**: `002-agent-memory` | **Date**: 2026-02-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-agent-memory/spec.md`

## Summary

实现 AI Agent 的记忆系统，具备"自我认知"与"记忆演化能力"。核心功能包括：
1. 身份初始化（SPIRIT.md、OWNER.md）与热加载
2. 多级上下文自动加载
3. 每日记忆记录与混合搜索
4. Markdown 与向量存储双写同步

技术方案：使用本地嵌入模型（sentence-transformers）+ sqlite-vss 实现向量检索，watchdog 监听文件变更实现热加载与双写同步。

## Technical Context

**Language/Version**: Python 3.11+ (后端), TypeScript (前端)
**Primary Dependencies**: FastAPI, SQLAlchemy, sentence-transformers, watchdog, sqlite-vss
**Storage**: SQLite + sqlite-vss (向量扩展)
**Testing**: pytest (后端), vitest (前端)
**Target Platform**: 本地服务器 (macOS/Linux/Windows)
**Project Type**: web (前后端分离)
**Performance Goals**: 向量检索 < 200ms, 热加载 < 100ms, 上下文加载 < 2s
**Constraints**: 本地运行, 单实例, 无外部 API 依赖
**Scale/Scope**: 10,000+ 记忆条目, 90 天日志保留

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 状态 | 说明 |
|------|------|------|
| I. 代码质量优先 | ✅ PASS | 使用类型注解, 遵循 PEP 8, 结构化日志 |
| II. 测试驱动开发 | ✅ PASS | pytest 覆盖率目标 80%+, 核心模块 90%+ |
| III. 关注点分离 | ✅ PASS | 分层架构: models/services/api, 横切关注点统一 |
| IV. 可调试性设计 | ✅ PASS | 结构化日志 JSON, 追踪 ID, 健康检查接口 |
| V. 用户体验一致性 | ✅ PASS | 统一响应格式, 错误提示包含修复建议 |
| VI. 性能优先 | ✅ PASS | 向量检索 < 200ms, 异步 I/O |
| VII. 组合优于继承 | ✅ PASS | 插件式工具系统, 依赖注入 |
| VIII. 稳定抽象原则 | ✅ PASS | 核心接口独立于具体实现 |
| IX. YAGNI 原则 | ✅ PASS | 仅实现 P1/P2 功能, P3 按需排期 |

**Gate Result**: ✅ ALL PASS - 可进入 Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/002-agent-memory/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── memory-api.yaml  # OpenAPI spec
├── checklists/
│   └── requirements.md  # Quality checklist
└── spec.md              # Feature specification
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── memory/                  # 新增: 记忆系统模块
│   │   ├── __init__.py
│   │   ├── spirit_loader.py     # SPIRIT.md/OWNER.md 加载
│   │   ├── context_builder.py   # 上下文构建器
│   │   ├── vector_store.py      # sqlite-vss 向量存储
│   │   ├── md_sync.py           # Markdown 双写同步
│   │   ├── hybrid_search.py     # 混合搜索实现
│   │   ├── file_watcher.py      # 文件监听器
│   │   └── models.py            # 记忆数据模型
│   ├── models/
│   │   └── memory.py            # 新增: 记忆相关 ORM 模型
│   ├── api/
│   │   └── v1/
│   │       └── memory.py        # 新增: 记忆 API 端点
│   └── services/
│       └── embedder.py          # 新增: 本地嵌入服务
└── tests/
    ├── unit/
    │   └── test_memory.py       # 新增: 记忆系统单元测试
    └── integration/
        └── test_memory_flow.py  # 新增: 集成测试

workspace/                       # 新增: 记忆文件目录
├── SPIRIT.md                    # AI 人格设定
├── OWNER.md                     # 用户画像
├── MEMORY.md                    # 长期记忆
├── TOOLS.md                     # 工具定义
└── memory/                      # 每日日志
    └── 2026-02-14.md
```

**Structure Decision**: 采用现有 web 项目结构，在 backend/src 下新增 memory/ 模块，workspace/ 作为记忆文件存储目录。

## Complexity Tracking

> 无宪法违规，无需记录。
