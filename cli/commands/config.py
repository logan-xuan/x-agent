"""CLI config 命令 — 配置管理。

用法：
- x-agent config show    → 显示当前配置
- x-agent config set     → 修改配置项
- x-agent config reload  → 热重载配置
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ..config import CLIConfig

config_app = typer.Typer()
console = Console()


@config_app.command("show")
def config_show() -> None:
    """显示当前配置。"""
    config = CLIConfig.from_env()

    table = Table(title="X-Agent CLI 配置", show_header=True)
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="green")

    table.add_row("server_url", config.server_url)
    table.add_row("mode", config.mode)
    table.add_row("default_session_id", config.default_session_id or "(auto)")
    table.add_row("timeout", f"{config.timeout}s")
    table.add_row("show_thinking", str(config.show_thinking))
    table.add_row("show_tool_calls", str(config.show_tool_calls))

    console.print(table)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="配置项名称"),
    value: str = typer.Argument(help="配置值"),
) -> None:
    """修改配置项（通过环境变量）。

    提示用户设置对应的环境变量。
    """
    env_key = f"XAGENT_{key.upper()}"
    console.print(f"请设置环境变量: [cyan]export {env_key}={value}[/cyan]")
    console.print("[dim]配置将在下次启动时生效[/dim]")


@config_app.command("reload")
def config_reload() -> None:
    """热重载配置（Remote 模式）。"""
    import asyncio
    asyncio.run(_reload_config())


async def _reload_config() -> None:
    """调用 Backend API 重载配置。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.post("/api/v1/config/reload", timeout=config.timeout)
            if response.status_code == 200:
                console.print("[green]配置已重载[/green]")
            else:
                console.print(f"[red]重载失败: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
