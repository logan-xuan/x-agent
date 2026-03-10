"""CLI session 命令 — 会话管理。

用法：
- x-agent session list   → 列出所有会话
- x-agent session clear  → 清除会话历史
"""

from __future__ import annotations

import asyncio

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ..config import CLIConfig

session_app = typer.Typer()
console = Console()


@session_app.command("list")
def session_list() -> None:
    """列出所有会话。"""
    asyncio.run(_list_sessions())


async def _list_sessions() -> None:
    """从 Backend 获取会话列表。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.get("/api/v1/sessions", timeout=config.timeout)
            if response.status_code != 200:
                console.print(f"[red]获取会话列表失败: {response.status_code}[/red]")
                return

            data = response.json()
            sessions = data.get("data", {}).get("items", [])

            table = Table(title="会话列表", show_header=True)
            table.add_column("Session ID", style="cyan", max_width=36)
            table.add_column("标题", style="green")
            table.add_column("更新时间", style="dim")

            for session in sessions:
                table.add_row(
                    session.get("id", ""),
                    session.get("title", "(无标题)"),
                    session.get("updated_at", ""),
                )

            console.print(table)
            console.print(f"[dim]共 {len(sessions)} 个会话[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@session_app.command("clear")
def session_clear(
    session_id: str = typer.Argument(help="要删除的会话 ID"),
) -> None:
    """删除指定会话。"""
    asyncio.run(_delete_session(session_id))


async def _delete_session(session_id: str) -> None:
    """调用 Backend API 删除会话。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.delete(
                f"/api/v1/sessions/{session_id}",
                timeout=config.timeout,
            )
            if response.status_code == 200:
                console.print(f"[green]会话 {session_id} 已删除[/green]")
            elif response.status_code == 404:
                console.print(f"[yellow]会话 {session_id} 不存在[/yellow]")
            else:
                console.print(f"[red]删除失败: {response.status_code}[/red]")
    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
