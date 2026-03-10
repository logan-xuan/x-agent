---
name: cron-ops
description: "Use this skill whenever the user wants to create a scheduled/cron/timed task, have the agent periodically call LLM to generate content and notify the user, or manage existing cron tasks. Trigger phrases: '创建定时任务', '每X分钟执行', '定时写', '定时生成', '自动执行', '周期性', 'cron', 'every N minutes/hours'."
keywords:
  - cron
  - 定时任务
  - 定时执行
  - 定时写作
  - 定时生成
  - 每分钟
  - 每小时
  - 每天
  - 周期性
  - 自动执行
  - AgentInvoker
auto-trigger: true
priority: 1
---

# Cron 定时任务

## ⚠️ CRITICAL：必须严格遵守以下规则

**创建定时任务时，你必须且只能按以下两步执行，不得自行发挥：**

### ❌ 严禁以下做法（会导致任务无效）

- 禁止用模板字符串、f-string 硬编码故事/报告/内容（这不是调用 LLM）
- 禁止用 `subprocess` 调用其他脚本
- 禁止用 `print()` 输出内容作为通知
- 禁止用 `schedule` 库或 `threading` 自己实现调度
- 禁止用 `sys.path.insert` 硬编码绝对路径
- 禁止把函数定义为同步 `def`（必须是 `async def`）
- 禁止在 AgentInvoker 调用后，再额外用 `write_file` 工具或其他方式重复写文件（AgentInvoker 已自动保存并推送结果，重复写会导致文件路径错误）
- 禁止用 `Path(workspace_path)` 直接包裹未展开的路径字符串；必须用 `Path(workspace_path).expanduser().resolve()` 展开 `~`，否则会产生 `workspace/workspace/` 嵌套目录

---

## 第一步：创建任务文件

在 `workspace/jobs/` 下创建 Python 脚本，**必须完整复制以下模板，只修改 prompt 内容和文件保存路径**：

```python
"""任务描述。"""
import datetime
from pathlib import Path

async def run_task():
    from src.gateway.agent_invoker import AgentInvoker, InvokeSource  # type: ignore[import-not-found]
    from src.conversation.dao.bootstrap import DEFAULT_AGENT_ID  # type: ignore[import-not-found]
    from src.conversation.identity import ChannelType  # type: ignore[import-not-found]

    result = await AgentInvoker().invoke(
        content="【在此填写你的 prompt，描述要生成什么内容】",
        agent_id=DEFAULT_AGENT_ID,
        channel_type=ChannelType.WEB_CHAT,
        source=InvokeSource.CRON,
    )

    if result.error:
        return {"success": False, "error": result.error}

    # 可选：保存到文件
    # ⚠️ 必须用绝对路径！任务运行时工作目录是 backend/，相对路径会写错位置
    # 通过配置获取 workspace 绝对路径
    from src.config.manager import ConfigManager  # type: ignore[import-not-found]
    # ⚠️ 必须 expanduser().resolve()，否则 ~ 不展开会产生 workspace/workspace/ 嵌套
    workspace_path = Path(ConfigManager().config.workspace.path).expanduser().resolve()
    now = datetime.datetime.now()
    out = workspace_path / "output_dir"  # 修改 output_dir 为实际子目录名
    out.mkdir(parents=True, exist_ok=True)
    filepath = out / f"result_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath.write_text(result.response, encoding="utf-8")

    # AgentInvoker 会自动把 LLM 结果推送给用户，无需手动 notify
    return {"success": True, "filepath": str(filepath), "delivered": result.delivered}
```

**关键说明：**
- `AgentInvoker().invoke()` = 真正调用 LLM 生成内容，结果自动推送给用户
- 用户离线时自动暂存，重连后投递
- 函数必须是 `async def`，调度器会自动 await

## 第二步：注册定时任务

```bash
# 间隔格式（推荐）
x-agent cron create -n "任务名" -s "5m" -f "workspace:jobs/文件名.py:run_task" -y

# Cron 表达式（分 时 日 月 周）
x-agent cron create -n "任务名" -s "0 9 * * *" -f "workspace:jobs/文件名.py:run_task" -y
```

**`-s` 格式：** `30s` / `5m` / `1h` / `2d` 或 cron 表达式如 `0 9 * * *`（每天9点）

## 任务管理（CLI 命令）

```bash
x-agent cron list                  # 查看所有任务
x-agent cron run <名称>            # 立即执行（测试）
x-agent cron pause/resume <名称>   # 暂停/恢复
x-agent cron delete <名称> -f      # 删除
x-agent cron history -t <名称>     # 执行历史
```

## 任务内部控制自身生命周期

如果任务需要在满足条件后**自动暂停自身**（如写完第 10 集后停止），使用 `SchedulerManager`，**禁止用 subprocess 调用 CLI**：

```python
async def run_task():
    # ... 业务逻辑 ...

    # 满足条件时自动暂停任务自身
    if episode_num >= 10:
        from src.cron.manager import SchedulerManager  # type: ignore[import-not-found]
        manager = SchedulerManager()
        await manager.pause_task("任务名称")  # 传入创建时的 -n 名称
        return {"success": True, "message": "故事已完结，任务已暂停"}
```
