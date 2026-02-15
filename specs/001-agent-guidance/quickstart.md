# Quickstart: Agent 核心主引导流程

**Feature**: Agent 核心主引导流程  
**Version**: 1.0.0

---

## 快速开始

### 1. 初始化 Workspace

首次使用时，创建 workspace 目录结构：

```bash
# 创建 workspace 目录
mkdir -p workspace/memory

# 复制示例文件（从模板）
cp templates/AGENTS.md.example workspace/AGENTS.md
cp templates/SPIRIT.md.example workspace/SPIRIT.md
cp templates/OWNER.md.example workspace/OWNER.md
```

### 2. 配置 AGENTS.md

编辑 `workspace/AGENTS.md`，定义 Agent 的行为规范：

```markdown
# AGENTS.md - 你的工作空间

## 首次启动

如果存在 `BOOTSTRAP.md`，那是你的"出生证明"。遵循它的指引，弄清楚你是谁，然后删除它。

## 每次会话开始时

在做任何事之前，请先：
1. 阅读 `SPIRIT.md` —— 这定义了你是谁
2. 阅读 `OWNER.md` —— 这定义了你在帮助谁
3. 阅读 `memory/YYYY-MM-DD.md`（今天 + 昨天）获取近期上下文
4. **如果处于主会话中**：还需阅读 `MEMORY.md`

## 记忆系统

- **每日笔记**：`memory/YYYY-MM-DD.md` —— 记录当日原始日志
- **长期记忆**：`MEMORY.md` —— 你精心整理的记忆

## 安全准则

- 永远不要泄露私有数据
- 未经确认，不要执行破坏性命令
- 优先使用 `trash` 而非 `rm`

## 外部操作 vs 内部操作

**可自由执行**：
- 读取文件、探索、整理、学习
- 搜索网络、查看日历
- 在工作空间内进行操作

**需先询问**：
- 发送邮件、推文、公开帖子
- 任何会离开本机的操作
```

### 3. 配置 SPIRIT.md

编辑 `workspace/SPIRIT.md`，定义 Agent 的身份：

```markdown
# SPIRIT.md

## 你是谁

你是 Qoder，一个强大的 AI 编程助手。

## 你的能力

- 代码编写与调试
- 架构设计与评审
- 技术调研与分析

## 你的风格

- 简洁直接，避免冗长
- 优先提供可运行的代码
- 主动考虑边缘情况
```

### 4. 配置 OWNER.md

编辑 `workspace/OWNER.md`，定义用户信息：

```markdown
# OWNER.md

## 用户基本信息

- **姓名**: [你的名字]
- **角色**: [开发者/产品经理/...]
- **技术栈**: Python, TypeScript, React, ...

## 工作偏好

- 喜欢简洁的回复
- 偏好中文交流
- 重视代码质量

## 重要背景

- 正在开发 X-Agent 项目
- 关注 AI Agent 技术
```

### 5. 启动 Agent

```bash
# 启动后端服务
cd backend
python -m src.main

# 或使用启动脚本
./start-backend.sh
```

---

## API 使用示例

### 加载上下文

```bash
curl -X POST http://localhost:8000/api/v1/context/load \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "session_type": "main",
    "workspace_path": "./workspace"
  }'
```

**响应示例**：

```json
{
  "success": true,
  "session_id": "session-001",
  "session_type": "main",
  "loaded_files": [
    {
      "file_path": "workspace/AGENTS.md",
      "success": true,
      "from_cache": false
    },
    {
      "file_path": "workspace/SPIRIT.md",
      "success": true,
      "from_cache": false
    },
    {
      "file_path": "workspace/MEMORY.md",
      "success": true,
      "from_cache": false
    }
  ],
  "context_version": "v1-20260215-143022",
  "load_time_ms": 45
}
```

### 重载 AGENTS.md

```bash
curl -X POST http://localhost:8000/api/v1/context/reload \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001"
  }'
```

**响应示例**：

```json
{
  "success": true,
  "reloaded": true,
  "previous_version": "v1-20260215-143022",
  "current_version": "v1-20260215-143530",
  "reload_time_ms": 12
}
```

### 检测会话类型

```bash
curl -X POST http://localhost:8000/api/v1/session/detect \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "direct",
    "user_count": 1
  }'
```

**响应示例**：

```json
{
  "session_type": "main",
  "confidence": 0.95,
  "reasoning": "单用户直接对话，判定为主会话"
}
```

---

## 文件说明

### 核心文件

| 文件 | 必需 | 主会话 Only | 说明 |
|------|------|-------------|------|
| AGENTS.md | ✅ | ❌ | 主引导文件，定义行为规范 |
| SPIRIT.md | ✅ | ❌ | Agent 身份定义 |
| OWNER.md | ✅ | ❌ | 用户信息 |
| TOOLS.md | ❌ | ❌ | 工具配置 |
| MEMORY.md | ❌ | ✅ | 长期记忆 |
| BOOTSTRAP.md | ❌ | ❌ | 首次启动引导（一次性） |

### 每日笔记

位于 `workspace/memory/` 目录，文件名格式：`YYYY-MM-DD.md`

Agent 自动加载今日和昨日的笔记。

---

## 故障排查

### 文件未加载

**症状**: API 返回 `loaded_files` 为空

**排查步骤**:
1. 检查文件路径是否正确
2. 确认文件有读取权限
3. 查看服务器日志获取详细错误

### 会话类型检测错误

**症状**: 共享上下文中加载了 MEMORY.md

**排查步骤**:
1. 检查 `channel_type` 参数
2. 验证 `user_count` 是否正确
3. 查看检测日志中的 `reasoning` 字段

### 重载延迟过高

**症状**: `reload_time_ms` > 1000ms

**排查步骤**:
1. 检查文件大小是否过大（建议 < 1MB）
2. 确认磁盘 I/O 性能
3. 启用缓存减少重复读取

---

## 配置选项

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WORKSPACE_PATH` | `./workspace` | workspace 目录路径 |
| `CONTEXT_CACHE_TTL` | `60` | 上下文缓存时间（秒） |
| `MAX_FILE_SIZE_MB` | `1` | 单文件大小限制（MB） |
| `MAINTENANCE_INTERVAL_HOURS` | `24` | 记忆维护间隔（小时） |

### 配置文件

`backend/config.yaml`:

```yaml
context:
  workspace_path: "./workspace"
  cache_ttl: 60
  max_file_size_mb: 1
  
maintenance:
  interval_hours: 24
  days_to_process: 7
  
security:
  allow_symlinks: false
  check_path_traversal: true
```

---

## 下一步

- 阅读 [data-model.md](./data-model.md) 了解数据结构
- 查看 [contracts/agent-context-api.yaml](./contracts/agent-context-api.yaml) 获取完整 API 文档
- 运行测试：`pytest tests/unit/test_context_loader.py`
