"""X-Agent CLI 入口。

使用 Typer 构建命令行界面，提供以下命令组：
- chat: 对话（核心功能）
- config: 配置管理
- tools: 工具管理
- session: 会话管理
- agent: Agent 管理
- cron: 定时任务管理
- status: 系统状态

用法::

    x-agent chat                      # 交互式对话
    x-agent chat "你好"               # 单次对话
    x-agent config show               # 查看配置
    x-agent status                    # 系统状态
    x-agent cron list                 # 查看定时任务
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="x-agent",
    help="""X-Agent CLI - AI Agent 命令行交互端

[bold]核心命令:[/bold]
  [green]chat[/green]     与 Agent 对话（支持单次/交互式）
  [green]agent[/green]    管理多智能体（创建/查看）
  [green]cron[/green]     定时任务管理（创建/执行/暂停/恢复/删除）

[bold]辅助命令:[/bold]
  [green]config[/green]   配置管理（查看/设置/重载）
  [green]tools[/green]    查看可用工具/Skills
  [green]session[/green]  会话管理（列表/清除）
  [green]status[/green]   系统状态检查

[bold]快速开始:[/bold]
  x-agent chat "你好，请帮我写一段 Python 代码"
  x-agent agent create -n "代码助手"
  x-agent cron create -n "备份" -s "0 2 * * *" -f "workspace:backup.py:run" -y
  x-agent status

[dim]使用 'x-agent <command> --help' 查看具体命令的详细用法[/dim]
""",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _register_commands() -> None:
    """延迟注册所有子命令，避免循环导入。"""
    from .commands.chat import chat_app
    from .commands.config import config_app
    from .commands.tools import tools_app
    from .commands.session import session_app
    from .commands.agent import agent_app
    from .commands.status import status_app
    from .commands.cron import cron_app

    app.add_typer(chat_app, name="chat", help="对话命令")
    app.add_typer(config_app, name="config", help="配置管理")
    app.add_typer(tools_app, name="tools", help="工具管理")
    app.add_typer(session_app, name="session", help="会话管理")
    app.add_typer(agent_app, name="agent", help="Agent 管理")
    app.add_typer(status_app, name="status", help="系统状态")
    app.add_typer(cron_app, name="cron", help="定时任务管理")


_register_commands()


@app.callback()
def main_callback() -> None:
    """X-Agent CLI - AI Agent 命令行交互端。
    
    提示：使用 'x-agent <command> --help' 查看具体命令的详细用法
    """


if __name__ == "__main__":
    app()
