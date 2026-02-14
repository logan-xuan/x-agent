# Quick Start: AI Agent 记忆系统

**Feature**: 002-agent-memory | **Date**: 2026-02-14

## 前置条件

- Python 3.11+
- 已完成 X-Agent MVP 基础功能（分支 001-x-agent-mvp）
- SQLite 3.38+（支持 JSON 函数）

## 安装依赖

```bash
cd backend

# 安装新增依赖
pip install sentence-transformers watchdog pyyaml python-frontmatter

# 或使用 pyproject.toml
pip install -e .
```

## 初始化

### 1. 创建工作目录

```bash
# 在项目根目录创建
mkdir -p workspace/memory
```

### 2. 初始化身份文件

首次启动时，系统会自动发起身份初始化对话：

```
AI: 您好！我是您的 AI 助手。为了更好地为您服务，我需要了解一些信息。
    请问您的姓名是？

用户: 张三

AI: 您好，张三！请问您是做什么工作的？

用户: 我是一名前端工程师

AI: 了解！请问您有什么特别的兴趣或爱好吗？

用户: 我喜欢编程、咖啡和徒步旅行

AI: 很好的爱好！请问您希望我扮演什么样的角色？

用户: 一个温和、理性的编程助手

AI: 好的，我已经记录了您的信息。让我们开始吧！
```

### 3. 手动创建身份文件（可选）

如果跳过交互式初始化，可以手动创建：

**workspace/SPIRIT.md**:
```markdown
# AI 人格设定

## 角色定位
我是一个专注型 AI 助手，服务于个人知识管理。

## 性格特征
温和、理性、主动但不过度打扰

## 价值观
- 尊重隐私
- 不编造信息
- 帮助用户变得更好

## 行为准则
- 在每次响应前，先回顾当前上下文和长期记忆
- 对重要计划进行提醒
- 拒绝不合理请求（如执行危险命令）
```

**workspace/OWNER.md**:
```markdown
# 用户画像

## 基本信息
- 姓名: 张三
- 年龄: 32
- 职业: 前端工程师

## 兴趣爱好
- 编程
- 咖啡
- 徒步旅行

## 当前目标
- 开发一款本地 AI 笔记工具

## 偏好设置
- 喜欢简洁 UI
- 不喜欢拿铁，只喝美式
```

## 快速测试

### 1. 启动服务

```bash
# 启动后端
cd backend
python -m src.main

# 启动前端（另一个终端）
cd frontend
npm run dev
```

### 2. 测试 API

```bash
# 检查身份状态
curl http://localhost:8000/api/v1/identity/status

# 加载上下文
curl -X POST http://localhost:8000/api/v1/context/load

# 创建记忆条目
curl -X POST http://localhost:8000/api/v1/memory/entries \
  -H "Content-Type: application/json" \
  -d '{
    "content": "用户决定使用 React 作为前端框架",
    "content_type": "decision"
  }'

# 搜索记忆
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "前端框架选择"
  }'
```

### 3. 测试热加载

```bash
# 修改 OWNER.md
echo "- 新增爱好：阅读科幻小说" >> workspace/OWNER.md

# 检查是否自动加载（无需重启）
curl http://localhost:8000/api/v1/identity/owner
```

## 文件结构

```
workspace/
├── SPIRIT.md          # AI 人格设定
├── OWNER.md           # 用户画像
├── MEMORY.md          # 长期记忆摘要
├── TOOLS.md           # 工具定义
└── memory/            # 每日日志
    ├── 2026-02-14.md
    └── 2026-02-15.md
```

## 常见问题

### Q: 如何手动标记重要对话？

**方式一**: 在对话中使用关键词
```
用户: 这很重要，我们决定下周开始重构。
```

**方式二**: 通过 API 创建
```bash
curl -X POST http://localhost:8000/api/v1/memory/entries \
  -H "Content-Type: application/json" \
  -d '{
    "content": "决定下周开始重构",
    "content_type": "manual"
  }'
```

### Q: 如何更新用户画像？

**方式一**: 对话更新
```
用户: 我的职业变了，现在是产品经理
AI: 好的，我已更新您的职业信息。
```

**方式二**: 手动编辑 OWNER.md

修改文件后系统自动热加载。

### Q: 记忆文件损坏怎么办？

系统会自动从向量存储重建损坏的 Markdown 文件。手动触发：

```bash
curl -X POST http://localhost:8000/api/v1/memory/rebuild
```

## 性能指标

| 指标 | 目标值 |
|------|--------|
| 上下文加载 | < 2s |
| 向量检索 | < 200ms |
| 热加载 | < 100ms |
| 混合搜索准确率 | > 85% |

## 下一步

1. 查看 [data-model.md](./data-model.md) 了解数据结构
2. 查看 [contracts/memory-api.yaml](./contracts/memory-api.yaml) 了解完整 API
3. 执行 `/speckit.tasks` 生成开发任务清单
