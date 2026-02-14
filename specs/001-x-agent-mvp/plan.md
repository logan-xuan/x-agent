# Implementation Plan: X-Agent MVP

**Branch**: `001-x-agent-mvp` | **Date**: 2026-02-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-x-agent-mvp/spec.md`

## Summary

构建 X-Agent MVP 版本，实现个人电脑部署的 AI Agent 基础功能。核心交付物包括：
1. **高内聚配置系统**: 统一的 `x-agent.yaml` 配置管理，支持多模型一主多备自动切换，厂商无关的抽象设计
2. 模块化 + 插件式架构的工程基础
3. WebChat 对话界面（React + TypeScript）
4. 后端服务（Python）支持 WebSocket 实时通信
5. 大语言模型集成（支持一主多备）
6. 对话历史持久化存储

## Technical Context

**Language/Version**: Python 3.11+ (后端), TypeScript 5.x (前端)  
**Primary Dependencies**: 
- 后端: FastAPI (Web框架), WebSockets (实时通信), SQLAlchemy (ORM), Pydantic (数据验证), PyYAML (配置解析)
- 前端: React 18, Vite (构建工具), Tailwind CSS (样式), shadcn/ui (组件库)
- LLM: OpenAI SDK / 阿里云百炼 SDK (模型调用)
- 配置: Pydantic-Settings + PyYAML，支持热重载和验证
**Storage**: SQLite (对话历史、配置存储)  
**Testing**: pytest (后端), Vitest (前端单元测试), Playwright (E2E测试)  
**Target Platform**: macOS / Linux / Windows (个人电脑本地部署)
**Project Type**: Web application (frontend + backend)  
**Performance Goals**: 
- AI 首字节返回 < 3秒 (平均), < 5秒 (95%分位)
- WebSocket 连接建立 < 1秒
- 页面首屏加载 < 2秒
**Constraints**: 
- 单用户本地部署 (MVP 阶段)
- 内存使用 < 500MB
- 支持离线配置编辑，在线生效（配置文件变更自动检测）
- 配置不依赖环境变量，统一 YAML 管理
- 模型配置厂商无关，支持一主多备自动故障转移
**Scale/Scope**: 
- 单用户并发会话
- 支持 1000+ 条历史消息存储
- 插件接口预留，MVP 不实现具体插件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 检查项 | 状态 | 说明 |
|------|--------|------|------|
| I. 代码质量优先 | 静态检查工具配置 | ✅ | 配置 ruff (Python) + ESLint (TS) |
| I. 代码质量优先 | 类型注解全覆盖 | ✅ | Pydantic + TypeScript 严格模式 |
| II. 测试驱动开发 | 测试框架选型 | ✅ | pytest + Vitest |
| II. 测试驱动开发 | 覆盖率目标 | ✅ | 后端 80%+, 核心模块 90%+ |
| III. 关注点分离 | 模块边界定义 | ✅ | 表达/网关/核心/工具/数据五层架构 |
| III. 关注点分离 | 禁止循环依赖 | ⚠️ | 需在设计阶段验证 |
| IV. 可调试性设计 | 结构化日志 | ✅ | 采用 JSON 格式日志 |
| IV. 可调试性设计 | 追踪 ID | ✅ | WebSocket 连接级上下文 ID |
| V. 用户体验一致性 | 统一响应格式 | ✅ | 定义标准 API 响应结构 |
| V. 用户体验一致性 | 状态反馈 | ✅ | 所有操作返回明确状态 |
| VI. 性能优先 | 流式响应 | ✅ | LLM SSE 流式输出 |
| VI. 性能优先 | 异步 I/O | ✅ | FastAPI 原生异步支持 |
| VII. 组合优于继承 | 插件接口设计 | ✅ | 定义标准插件契约 |
| VIII. 稳定抽象原则 | 接口契约定义 | ✅ | 核心模块接口先行定义 |
| VIII. 稳定抽象原则 | 配置抽象层 | ✅ | LLM Provider 抽象，厂商无关 |
| IX. YAGNI 原则 | 功能范围控制 | ✅ | MVP 仅实现 P0 需求 |
| IX. YAGNI 原则 | 配置不过度设计 | ✅ | 统一 YAML 管理，无需复杂配置中心 |

**检查结果**: 所有原则已纳入设计考量，无违规项。

### 配置系统专项设计原则

| 设计目标 | 实现方式 | 符合原则 |
|----------|----------|----------|
| 高内聚 | 配置管理独立模块，包含加载/验证/监听/热重载 | III. 关注点分离 |
| 易维护 | YAML 格式，注释支持，类型验证，错误即时反馈 | I. 代码质量优先 |
| 厂商无关 | 统一 ModelConfig 抽象，支持任意 OpenAI 兼容 API | VIII. 稳定抽象原则 |
| 一主多备 | 内置故障转移逻辑，自动切换备用模型 | VI. 性能优先 |
| 灵活扩展 | 新增模型只需修改配置，无需代码变更 | VII. 组合优于继承 |
| 热重载 | 文件变更自动检测，无需重启服务 | V. 用户体验一致性 |

## Project Structure

### Documentation (this feature)

```text
specs/001-x-agent-mvp/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/                          # Python 后端服务
├── src/
│   ├── __init__.py
│   ├── main.py                   # FastAPI 应用入口
│   ├── config/                   # 配置管理模块 (高内聚设计)
│   │   ├── __init__.py
│   │   ├── manager.py            # 配置管理器 (热重载、验证)
│   │   ├── models.py             # Pydantic 配置模型
│   │   ├── loader.py             # YAML 加载器
│   │   └── watcher.py            # 文件变更监听器
│   ├── api/                      # API 层 (路由定义)
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py           # 聊天相关 API
│   │   │   └── health.py         # 健康检查
│   │   └── websocket.py          # WebSocket 处理
│   ├── core/                     # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── agent.py              # Agent 核心
│   │   ├── context.py            # 上下文管理
│   │   └── session.py            # 会话管理
│   ├── models/                   # 数据模型 (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── message.py
│   │   └── session.py
│   ├── services/                 # 业务服务层
│   │   ├── __init__.py
│   │   ├── llm/                  # LLM 服务 (多模型支持)
│   │   │   ├── __init__.py
│   │   │   ├── provider.py       # LLM Provider 抽象基类
│   │   │   ├── openai_provider.py    # OpenAI 实现
│   │   │   ├── bailian_provider.py   # 阿里云百炼实现
│   │   │   ├── router.py         # 一主多备路由
│   │   │   └── failover.py       # 故障转移逻辑
│   │   └── storage.py            # 存储服务
│   ├── plugins/                  # 插件接口 (MVP 预留)
│   │   ├── __init__.py
│   │   └── base.py               # 插件基类/接口
│   └── utils/                    # 工具函数
│       ├── __init__.py
│       └── logger.py             # 结构化日志
├── tests/
│   ├── __init__.py
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── pyproject.toml                # Python 依赖管理
└── x-agent.yaml                  # 配置文件模板

frontend/                         # React + TypeScript 前端
├── src/
│   ├── components/               # UI 组件
│   │   ├── chat/                 # 聊天相关组件
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   └── MessageItem.tsx
│   │   └── ui/                   # 通用 UI 组件 (shadcn)
│   ├── hooks/                    # 自定义 Hooks
│   │   ├── useWebSocket.ts
│   │   └── useChat.ts
│   ├── services/                 # API 服务
│   │   ├── api.ts
│   │   └── websocket.ts
│   ├── types/                    # TypeScript 类型定义
│   │   └── index.ts
│   ├── utils/                    # 工具函数
│   │   └── logger.ts
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── tests/
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

**Structure Decision**: 采用 Web application 结构，前后端分离部署。后端采用分层架构（API → Core → Services → Models），前端采用组件化架构。符合宪法"关注点分离"和"模块化"原则。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 分层架构 (5层) | 满足模块化要求，确保各层职责单一 | 简单 MVC 会导致业务逻辑与基础设施耦合，违反关注点分离原则 |
| 前后端分离 | 技术栈不同 (Python/TS)，独立部署和维护 | 单体应用无法满足前端现代化开发需求，且违背技术选型约束 |

---

## Phase 0: Research

### 技术选型决策

#### 后端框架: FastAPI

**决策**: 采用 FastAPI 作为后端 Web 框架

**理由**:
- 原生异步支持，符合性能优先原则
- 自动 API 文档生成 (OpenAPI/Swagger)
- Pydantic 集成，类型安全
- WebSocket 支持完善
- 社区活跃，文档丰富

**替代方案考虑**:
- Flask: 需要额外配置异步，生态相对老旧
- Django: 过于重量级，不符合 YAGNI 原则
- Tornado: 维护活跃度下降

#### 前端框架: React + Vite

**决策**: 采用 React 18 + Vite 构建工具

**理由**:
- React 生态成熟，组件化开发符合关注点分离
- Vite 构建速度快，开发体验好
- 支持 TypeScript 严格模式
- 与 shadcn/ui 组件库兼容

**替代方案考虑**:
- Vue: 同样优秀，但 React 生态更丰富
- Svelte: 较新，长期维护风险
- Next.js: 过于重量级，MVP 不需要 SSR

#### 数据库: SQLite

**决策**: 采用 SQLite 作为数据存储

**理由**:
- 零配置，适合个人本地部署
- 单文件存储，备份简单
- MVP 阶段数据量小，性能足够
- 后续可无缝迁移到 PostgreSQL

**替代方案考虑**:
- PostgreSQL: 需要额外安装配置，增加部署复杂度
- MongoDB: 关系型数据更适合对话历史存储

#### LLM SDK: OpenAI SDK + 阿里云百炼 SDK

**决策**: 同时支持 OpenAI 格式和阿里云百炼

**理由**:
- OpenAI SDK 是行业标准，兼容多数模型提供商
- 阿里云百炼是国内优质选择，需要原生支持
- 通过统一抽象层封装，支持一主多备切换

---

## Phase 1: Design

### 数据模型设计

详见 [data-model.md](./data-model.md)

### API 契约

详见 [contracts/](./contracts/)

### 快速开始指南

详见 [quickstart.md](./quickstart.md)
