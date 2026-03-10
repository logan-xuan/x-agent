"""CLI status 命令 — 系统状态。

用法：
- x-agent status   → 查看系统状态
"""

from __future__ import annotations

import asyncio

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

from ..config import CLIConfig

status_app = typer.Typer(invoke_without_command=True)
console = Console()


@status_app.callback(invoke_without_command=True)
def status() -> None:
    """查看系统状态。"""
    asyncio.run(_check_status())


async def _check_status() -> None:
    """检查 Backend 健康状态。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.get("/api/v1/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                health_status = data.get("status", "unknown")
                version = data.get("version", "unknown")

                console.print(Panel(
                    f"[green]● 在线[/green]\n"
                    f"[bold]服务地址:[/bold] {config.server_url}\n"
                    f"[bold]状态:[/bold] {health_status}\n"
                    f"[bold]版本:[/bold] {version}\n"
                    f"[bold]模式:[/bold] {config.mode}",
                    title="X-Agent 状态",
                    border_style="green",
                ))
            else:
                console.print(Panel(
                    f"[yellow]● 异常[/yellow]\n"
                    f"[bold]服务地址:[/bold] {config.server_url}\n"
                    f"[bold]HTTP 状态码:[/bold] {response.status_code}",
                    title="X-Agent 状态",
                    border_style="yellow",
                ))
    except httpx.ConnectError:
        console.print(Panel(
            f"[red]● 离线[/red]\n"
            f"[bold]服务地址:[/bold] {config.server_url}\n"
            f"[bold]错误:[/bold] 无法连接到服务",
            title="X-Agent 状态",
            border_style="red",
        ))
