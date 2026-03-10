# X-Agent CLI

X-Agent 命令行工具，用于与 AI Agent 交互、管理配置和系统状态。

## 安装

```bash
# 进入 cli 目录
cd cli

# 安装依赖
pip install -r requirements.txt  # 或 pip install -e .

# 验证安装
x-agent --help
```

## 快速开始

```bash
# 查看系统状态
x-agent status

# 创建新 Agent
x-agent agent create --name "我的助手"

# 开始对话
x-agent chat
```

## 命令参考

### `chat` — 对话功能

与 Agent 进行交互式或单次对话。

```bash
# 交互式对话（默认）
x-agent chat

# 单次对话
x-agent chat "你好，请帮我写一段 Python 代码"

# 指定会话
x-agent chat --session <session_id>

# 强制新建会话
x-agent chat --new

# 指定 Agent
x-agent chat --agent "代码助手"
x-agent chat --agent-id <agent_id>
```

**参数：**
| 参数 | 简写 | 说明 |
|------|------|------|
| `--session` | `-s` | 指定会话 ID |
| `--new` | `-n` | 强制新建会话 |
| `--agent` | `-a` | 指定 Agent 名称 |
| `--agent-id` | | 指定 Agent ID |

---

### `agent` — Agent 管理

管理多智能体，包括创建、查看列表和详情。

```bash
# 创建新 Agent（交互式）
x-agent agent create

# 指定参数创建
x-agent agent create --name "代码助手"
x-agent agent create --name "代码助手" --agent-id code-assistant
x-agent agent create \
  --name "代码助手" \
  --agent-id code-assistant \
  --persona "你是一个专注于代码审查的 AI 助手" \
  --workspace ./agents/code-assistant

# 列出所有 Agent
x-agent agent list

# 查看 Agent 详情
x-agent agent info <agent_id>
```

**`create` 参数：**
| 参数 | 简写 | 说明 |
|------|------|------|
| `--name` | `-n` | Agent 名称（必填，可交互输入） |
| `--agent-id` | `-i` | Agent ID（可选，默认根据名称自动生成） |
| `--persona` | `-p` | 人设描述（可选，默认使用通用描述） |
| `--workspace` | `-w` | 工作空间路径（可选，默认 `./agents/<agent_id>`） |

**Agent ID 生成规则：**
- 转为小写
- 空格和特殊字符替换为下划线
- 连续下划线合并，首尾去除下划线
- 示例：`"我的助手"` → `我的助手` → `"my_assistant"`

**创建的工作空间结构：**
```
./agents/<agent_id>/
├── agent.yaml          # Agent 配置
├── AGENTS.md           # 工作空间使用指南
├── BOOTSTRAP.md        # 首次启动引导
├── SPIRIT.md           # 人格设定
├── IDENTITY.md         # 身份信息
├── OWNER.md            # 用户画像
├── MEMORY.md           # 长期记忆
├── TOOLS.md            # 工具定义
├── HEARTBEAT.md        # 心跳任务
└── memory/
    └── YYYY-MM-DD.md   # 每日记忆
```

---

### `config` — 配置管理

查看和修改 CLI 配置。

```bash
# 显示当前配置
x-agent config show

# 设置配置项（通过环境变量）
x-agent config set <key> <value>

# 热重载配置（Remote 模式）
x-agent config reload
```

**配置项：**
| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `XAGENT_SERVER_URL` | Backend 服务地址 | `http://localhost:5177` |
| `XAGENT_MODE` | 运行模式 (`remote`/`embedded`) | `remote` |
| `XAGENT_SESSION_ID` | 默认会话 ID | `None`（自动创建） |
| `XAGENT_TIMEOUT` | HTTP 请求超时（秒） | `300` |
| `XAGENT_SHOW_THINKING` | 是否显示思考过程 | `false` |
| `XAGENT_SHOW_TOOL_CALLS` | 是否显示工具调用详情 | `true` |
| `XAGENT_ADMIN_TOKEN` | Admin API 认证令牌 | `x-agent-admin-token-88888` |

---

### `session` — 会话管理

管理对话会话。

```bash
# 列出所有会话
x-agent session list

# 删除指定会话
x-agent session clear <session_id>
```

---

### `cron` — 定时任务管理

管理定时任务（Cron Jobs），支持创建、执行、暂停、恢复、删除和查看历史。

```bash
# 列出所有定时任务
x-agent cron list

# 交互式创建（逐步提示输入各参数）
x-agent cron create

# 非交互式创建（-y 跳过所有确认）
x-agent cron create -n "每日备份" \
    -s "0 2 * * *" \
    -f "workspace:backup.py:run" \
    -d "每天凌晨 2 点执行备份" -y

# 立即执行任务
x-agent cron run <task_id>

# 暂停任务
x-agent cron pause <task_id>

# 恢复任务
x-agent cron resume <task_id>

# 删除任务
x-agent cron delete <task_id>
x-agent cron delete <task_id> -f  # 强制删除，跳过确认

# 查看执行历史
x-agent cron history
x-agent cron history -t <task_id>  # 查看指定任务历史

# 查看任务详情
x-agent cron info <task_id>
```

**`create` 参数说明：**
| 参数 | 简写 | 必填 | 说明 |
|------|------|------|------|
| `--name` | `-n` | ✅ | 任务名称（也用于生成任务 ID） |
| `--schedule` | `-s` | ✅ | 定时表达式：cron 格式 `'0 2 * * *'` 或间隔格式 `'30m'/'1h'/'2d'` |
| `--func` | `-f` | ✅ | 函数路径：`workspace:backup.py:run` / `/abs/path.py:main` |
| `--desc` | `-d` | ❌ | 任务描述。`-d "xxx"` 直接使用；`-y` 模式未传则默认为空；交互模式会提示输入（可留空） |
| `--enabled` | | ❌ | 是否立即启用，默认 `true` |
| `--yes` | `-y` | ❌ | 跳过所有交互确认，直接创建。需同时提供 `-n`、`-s`、`-f` |

**定时表达式格式：**
- **Cron 格式**：`分 时 日 月 周`，如 `0 2 * * *`（每天凌晨 2 点）
- **间隔格式**：`30m`（30 分钟）、`1h`（1 小时）、`2d`（2 天）

**func 路径格式：**
- `workspace:my_task.py:run_task` → workspace 相对路径
- `/abs/path/script.py:main` → 绝对路径
- `my_task.py:run_task` → 自动在 `workspace/jobs/` 下查找

**`--desc/-d` 参数行为：**
- `-d "xxx"`：直接使用提供的描述
- `-y` 但未传 `-d`：描述默认为空，不弹交互
- 交互模式（无 `-y`）：提示输入描述，可留空

---

### `tools` — 工具管理

查看可用的 Skills/工具。

```bash
# 列出所有工具
x-agent tools list

# 查看工具详情
x-agent tools info <name>
```

---

### `status` — 系统状态

查看 Backend 服务连接状态和健康信息。

```bash
x-agent status
```

输出示例：
```
┌─────────────────────────────────────┐
│ X-Agent 状态                        │
├─────────────────────────────────────┤
│ ● 在线                              │
│ 服务地址: http://localhost:5177     │
│ 状态: healthy                       │
│ 版本: 1.0.0                         │
│ 模式: remote                        │
└─────────────────────────────────────┘
```

---

## 环境配置

创建 `.env` 文件或导出环境变量：

```bash
export XAGENT_SERVER_URL=http://localhost:5177
export XAGENT_ADMIN_TOKEN=your-admin-token
export XAGENT_TIMEOUT=300
```

## 完整命令树

```
x-agent
├── chat [message] [--session/-s] [--new/-n] [--agent/-a] [--agent-id]
├── agent
│   ├── create [--name/-n] [--agent-id/-i] [--persona/-p] [--workspace/-w]
│   ├── list
│   └── info <agent_id>
├── config
│   ├── show
│   ├── set <key> <value>
│   └── reload
├── cron
│   ├── list [--enabled/-e] [--limit/-l]
│   ├── create [--name/-n] [--schedule/-s] [--func/-f] [--desc/-d] [--enabled] [--yes/-y]
│   ├── run <task_id>
│   ├── pause <task_id>
│   ├── resume <task_id>
│   ├── delete <task_id> [--force/-f]
│   ├── history [--task/-t] [--limit/-l]
│   └── info <task_id>
├── session
│   ├── list
│   └── clear <session_id>
├── tools
│   ├── list
│   └── info <name>
└── status
```

## 开发

```bash
# 本地开发模式
export XAGENT_MODE=embedded

# 运行测试
pytest

# 代码检查
ruff check .
ruff format .
```
