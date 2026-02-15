# Implementation Plan: Agent 核心主引导流程

**Branch**: `001-agent-guidance` | **Date**: 2026-02-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-agent-guidance/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

为 AI Agent 建立主引导流程，通过 `workspace/AGENTS.md` 作为核心入口文件，实现会话启动时的上下文自动加载、用户提问时的流程重载、以及定期记忆维护。系统需要支持主会话与共享上下文的区分，确保 MEMORY.md 的隐私安全。

## Technical Context

**Language/Version**: Python 3.11+ (后端), TypeScript (前端配置界面)  
**Primary Dependencies**: 
- 文件监控: `watchdog` (Python) 或 `chokidar` (Node.js)
- 定时任务: `APScheduler` (Python) 或 `node-cron`
- Markdown 解析: `markdown-it` 或 `mistune`
**Storage**: 文件系统 (workspace/ 目录下的 Markdown 文件)  
**Testing**: pytest (Python), Vitest (TypeScript)  
**Target Platform**: Linux/macOS/Windows (跨平台文件系统操作)
**Project Type**: 单项目，核心为文件系统操作与上下文管理  
**Performance Goals**: AGENTS.md 重载延迟 < 1000ms (SC-004)  
**Constraints**: 
- 文件 I/O 操作必须异步非阻塞
- 内存使用需控制，避免加载过多历史文件
- 必须支持并发会话的文件访问安全
**Scale/Scope**: 个人级使用，workspace 文件数量 < 1000，单文件大小 < 1MB

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 宪法原则 | 状态 | 说明 |
|---------|------|------|
| I. 代码质量优先 | ✅ PASS | 文件操作模块需类型注解，函数复杂度控制在 15 以内 |
| II. 测试驱动开发 | ✅ PASS | 文件加载、会话检测、重载机制需单元测试覆盖 |
| III. 关注点分离 | ✅ PASS | 文件 I/O、上下文构建、会话管理分层清晰 |
| IV. 可调试性设计 | ✅ PASS | 文件加载过程需记录结构化日志，包含文件路径和加载时间 |
| V. 用户体验一致性 | ✅ PASS | 文件缺失时自动创建并提示用户，禁止静默失败 |
| VI. 性能优先 | ✅ PASS | 重载延迟 < 1000ms 符合要求，文件 I/O 需异步 |
| VII. 组合优于继承 | ✅ PASS | 通过配置组合不同的上下文加载策略 |
| VIII. 稳定抽象原则 | ✅ PASS | 定义文件加载器接口，支持不同存储后端扩展 |
| IX. YAGNI 原则 | ✅ PASS | 聚焦核心功能：加载、重载、维护，无过度设计 |

**宪法合规结论**: ✅ 所有原则通过，可进入 Phase 0 研究阶段

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-guidance/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/src/
├── core/
│   ├── context_loader.py      # 上下文加载器核心
│   ├── session_detector.py    # 会话类型检测
│   └── file_watcher.py        # 文件监控与重载
├── services/
│   ├── guidance_service.py    # AGENTS.md 引导服务
│   ├── memory_maintenance.py  # 记忆维护任务
│   └── template_service.py    # 默认模板管理
├── models/
│   ├── context.py             # 上下文数据模型
│   └── session.py             # 会话类型定义
└── utils/
    └── file_utils.py          # 文件操作工具

workspace/                       # 用户工作空间
├── AGENTS.md                    # 主引导文件
├── SPIRIT.md                    # Agent 身份定义
├── OWNER.md                     # 用户信息
├── MEMORY.md                    # 长期记忆
├── TOOLS.md                     # 工具配置
├── BOOTSTRAP.md                 # 首次启动引导（一次性）
└── memory/                      # 每日笔记目录
    └── YYYY-MM-DD.md

tests/
├── unit/
│   ├── test_context_loader.py
│   ├── test_session_detector.py
│   └── test_file_watcher.py
└── integration/
    └── test_guidance_flow.py
```

**Structure Decision**: 采用单项目结构，核心模块位于 `backend/src/core/`，负责文件加载、会话检测和重载机制。用户工作空间 `workspace/` 包含所有上下文文件。

## Phase Completion Status

### Phase 0: Research ✅ COMPLETE

**输出**: [research.md](./research.md)

- 文件监控方案: `watchdog`
- 定时任务方案: `APScheduler`
- Markdown 解析: 标准库简单读取
- 性能策略: 异步 I/O + 缓存
- 安全策略: 文件锁 + 路径验证

### Phase 1: Design ✅ COMPLETE

**输出**:
- [data-model.md](./data-model.md) - 数据模型定义
- [contracts/agent-context-api.yaml](./contracts/agent-context-api.yaml) - OpenAPI 契约
- [quickstart.md](./quickstart.md) - 快速开始指南
- QODER.md - Agent 上下文已更新

### Phase 2: Tasks (Next)

**待执行**: `/speckit.tasks` 生成任务清单

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 无 | - | - |
