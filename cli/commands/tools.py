"""CLI tools 命令 — 工具管理。

用法：
- x-agent tools list       → 列出所有可用工具
- x-agent tools info <name> → 查看工具详情
"""

from __future__ import annotations

import asyncio

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ..config import CLIConfig

tools_app = typer.Typer()
console = Console()


@tools_app.command("list")
def tools_list() -> None:
    """列出所有可用工具。"""
    asyncio.run(_list_tools())


async def _list_tools() -> None:
    """从 Backend 获取工具（Skills）列表。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.get("/api/v1/skills", timeout=config.timeout)
            if response.status_code != 200:
                console.print(f"[red]获取工具列表失败: {response.status_code}[/red]")
                return

            skills = response.json()

            table = Table(title="可用工具（Skills）", show_header=True)
            table.add_column("#", style="dim")
            table.add_column("名称", style="cyan")
            table.add_column("来源", style="yellow")
            table.add_column("描述", style="green", max_width=50)

            for index, skill in enumerate(skills, 1):
                table.add_row(
                    str(index),
                    skill.get("name", ""),
                    skill.get("source", ""),
                    skill.get("description", "")[:50],
                )

            console.print(table)
            console.print(f"[dim]共 {len(skills)} 个工具[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@tools_app.command("info")
def tools_info(
    name: str = typer.Argument(help="工具名称"),
) -> None:
    """查看工具详情。"""
    asyncio.run(_get_tool_info(name))


async def _get_tool_info(name: str) -> None:
    """从 Backend 获取指定工具（Skill）的详情。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            response = await client.get("/api/v1/skills", timeout=config.timeout)
            if response.status_code != 200:
                console.print(f"[red]获取工具信息失败: {response.status_code}[/red]")
                return

            skills = response.json()
            matched = [s for s in skills if s.get("name") == name or s.get("skill_id") == name]

            if not matched:
                available_names = [s.get("name", "") for s in skills]
                console.print(f"[yellow]工具 '{name}' 未找到[/yellow]")
                console.print(f"[dim]可用工具: {', '.join(available_names)}[/dim]")
                return

            skill = matched[0]
            console.print(f"[bold cyan]名称:[/bold cyan] {skill.get('name', '')}")
            console.print(f"[bold]Skill ID:[/bold] {skill.get('skill_id', '')}")
            console.print(f"[bold]版本:[/bold] {skill.get('version', '')}")
            console.print(f"[bold]描述:[/bold] {skill.get('description', '')}")
            console.print(f"[bold]来源:[/bold] {skill.get('source', '')}")
            console.print(f"[bold]标签:[/bold] {', '.join(skill.get('tags', []))}")
            console.print(f"[bold]风险等级:[/bold] {skill.get('risk_level', '')}")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
