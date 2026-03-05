# Implementation Plan: Skill 系统重构

**Branch**: `001-skill-system-refactor` | **Date**: 2026-03-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-skill-system-refactor/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

重构 X-Agent 技能系统，实现统一的技能元数据模型（SkillManifest）、组件化架构、两级来源优先级机制（USER > SYSTEM）、智能语义检索和渐进式执行能力。通过 SkillAdapter 实现 SkillPort 接口与 agent-core 集成。

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Pydantic, sqlite-vss (向量检索), sentence-transformers (Embedding)  
**Storage**: 内存缓存 + 文件系统 (manifest.json + SKILL.md) + SQLite-VSS (向量索引)  
**Testing**: pytest  
**Target Platform**: Linux/macOS 服务器  
**Project Type**: Web 服务 (FastAPI backend)  
**Performance Goals**: 技能发现 < 200ms, 语义检索准确率 > 80%  
**Constraints**: 向量检索 < 200ms, 内存使用可控  
**Scale/Scope**: 50-100 技能规模, 单用户场景

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 评估 | 状态 |
|------|------|------|
| I. 代码质量优先 | 所有新代码需类型注解、文档字符串 | ✅ Pass |
| II. 测试驱动开发 | 需先写测试，覆盖率 > 80% | ✅ Pass |
| III. 关注点分离 | 组件化设计：Parser/Registry/Discovery/Scorer/Executor 分离 | ✅ Pass |
| IV. 可调试性设计 | 结构化日志 + trace_id 追踪 | ✅ Pass |
| V. 用户体验一致性 | SkillCard 统一输出格式 | ✅ Pass |
| VI. 性能优先 | 200ms 约束, 异步操作 | ✅ Pass |
| VII. 组合优于继承 | SkillAdapter 组合各组件，依赖注入 | ✅ Pass |
| VIII. 稳定抽象原则 | SkillPort 接口不变，组件实现可替换 | ✅ Pass |
| IX. YAGNI 原则 | 本期不实现 REMOTE 来源、热更新、版本管理 | ✅ Pass |

## Project Structure

### Documentation (this feature)

```text
specs/001-skill-system-refactor/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── agent_core/
│   │   ├── ports/
│   │   │   └── skill_port.py        # SkillPort 接口（已存在，需扩展）
│   │   └── adapters/
│   │       └── skill_adapter.py     # NEW: SkillAdapter 实现
│   ├── models/
│   │   └── skill.py                 # 统一 SkillManifest 定义
│   ├── services/
│   │   ├── skill/                   # NEW: 技能子模块
│   │   │   ├── __init__.py
│   │   │   ├── manifest_parser.py   # NEW: manifest.json 解析器
│   │   │   ├── registry.py          # 重构: 三级注册机制
│   │   │   ├── indexer.py           # NEW: 向量索引服务
│   │   │   ├── discovery.py         # NEW: 发现与检索服务
│   │   │   ├── scorer.py            # NEW: 混合评分器
│   │   │   └── executor.py          # NEW: 渐进执行器
│   │   ├── skill_parser.py          # 保留: SKILL.md 解析（兼容）
│   │   └── skill_registry.py        # 迁移至 skill/registry.py
│   └── skills/
│       └── [各技能目录]/
│           ├── manifest.json        # NEW: 技能清单
│           └── SKILL.md             # 保留: 人类可读指南
└── tests/
    ├── unit/
    │   └── services/
    │       └── skill/
    │           ├── test_manifest_parser.py
    │           ├── test_registry.py
    │           ├── test_indexer.py
    │           ├── test_discovery.py
    │           ├── test_scorer.py
    │           └── test_executor.py
    └── integration/
        └── test_skill_system.py
```

**Structure Decision**: 采用 Web 应用结构（backend/），在现有 services/ 下新增 skill/ 子模块，保持与现有代码兼容。agent_core/adapters/ 新增 SkillAdapter 实现 SkillPort 接口。

## Complexity Tracking

> **无宪法违规需要辩护**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | - | - |
