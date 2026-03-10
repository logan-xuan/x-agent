"""CLI agent 命令 — Agent 管理。

用法：
- x-agent agent list                        → 列出所有 Agent
- x-agent agent info <agent_id>             → 查看 Agent 详情
- x-agent agent create                      → 交互式创建新 Agent
- x-agent agent create --name "小助手"      → 指定名称创建
- x-agent agent create --name "小助手" \\
    --agent-id my-assistant \\
    --persona "你是一个友好的助手" \\
    --workspace ./agents/my-assistant       → 完整参数创建
"""

from __future__ import annotations

import asyncio

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ..config import CLIConfig
from .agent_workspace import create_agent_workspace

agent_app = typer.Typer()
console = Console()


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(None, "--name", "-n", help="Agent 名称"),
    agent_id: str = typer.Option(None, "--agent-id", "-i", help="Agent ID（留空则根据名称自动生成）"),
    persona: str = typer.Option(None, "--persona", "-p", help="Agent 人设描述"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="工作空间路径（留空则使用 ./agents/<agent_id>）"),
) -> None:
    """创建新的 Agent，初始化配置文件和工作空间模板。"""
    asyncio.run(_create_agent(name=name, agent_id=agent_id, persona=persona, workspace=workspace))


async def _create_agent(
    *,
    name: str | None,
    agent_id: str | None,
    persona: str | None,
    workspace: str | None,
) -> None:
    """交互式收集参数并创建 Agent。"""
    # ── 交互式补全缺失参数 ──────────────────────────────────────────────
    resolved_name: str = name if name else typer.prompt("Agent 名称")
    resolved_agent_id: str = agent_id if agent_id else _derive_agent_id(resolved_name)

    if not persona:
        console.print("[dim]提示：留空将使用默认人设[/dim]")
        raw_persona: str = typer.prompt("Agent 人设描述（可留空）", default="")
        resolved_persona: str = raw_persona.strip() if raw_persona.strip() else f"你是 {resolved_name}，一个智能 AI 助手。"
    else:
        resolved_persona: str = persona

    resolved_workspace = workspace or f"./agents/{resolved_agent_id}"

    # ── 预览确认 ────────────────────────────────────────────────────────
    console.print()
    console.print("[bold]即将创建 Agent：[/bold]")
    console.print(f"  [cyan]Agent ID:[/cyan]  {resolved_agent_id}")
    console.print(f"  [cyan]名称:[/cyan]      {resolved_name}")
    console.print(f"  [cyan]人设:[/cyan]      {resolved_persona}")
    console.print(f"  [cyan]工作空间:[/cyan]  {resolved_workspace}")
    console.print()

    confirmed = typer.confirm("确认创建？", default=True)
    if not confirmed:
        console.print("[yellow]已取消[/yellow]")
        return

    # ── 调用 Backend API 注册 Agent ─────────────────────────────────────
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.post(
                "/api/v1/admin/agents",
                headers=headers,
                json={
                    "agent_id": resolved_agent_id,
                    "agent_name": resolved_name,
                    "agent_persona": resolved_persona,
                    "workspace": resolved_workspace,
                },
                timeout=config.timeout,
            )
            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                console.print("[dim]可通过 XAGENT_ADMIN_TOKEN 环境变量设置[/dim]")
                return
            if response.status_code not in (200, 201):
                error_detail = response.text
                console.print(f"[red]创建 Agent 失败 ({response.status_code}): {error_detail}[/red]")
                return

            console.print(f"[green]✓ Agent 已在 Backend 注册成功[/green]")

    except httpx.ConnectError:
        console.print(f"[yellow]⚠ 无法连接到 {config.server_url}，跳过 Backend 注册，仅初始化本地工作空间[/yellow]")

    # ── 初始化本地工作空间 ───────────────────────────────────────────────
    created_files = create_agent_workspace(
        agent_id=resolved_agent_id,
        agent_name=resolved_name,
        persona=resolved_persona,
        workspace_path=resolved_workspace,
    )

    console.print()
    console.print(f"[bold green]✓ Agent '{resolved_name}' 创建完成！[/bold green]")
    console.print(f"[dim]工作空间：{resolved_workspace}[/dim]")
    console.print()
    console.print("[bold]已生成文件：[/bold]")
    for file_path in created_files:
        console.print(f"  [dim]•[/dim] {file_path}")


def _derive_agent_id(name: str) -> str:
    """根据 Agent 名称自动生成 agent_id。

    规则：
    - 转为小写
    - 中文字符转拼音首字母缩写（简单处理：直接保留 Unicode 范围内的字符）
    - 空格和特殊字符替换为下划线
    - 连续下划线合并，首尾去除下划线

    Args:
        name: Agent 名称。

    Returns:
        合法的 agent_id 字符串。
    """
    import re
    import unicodedata

    # 将 Unicode 字符规范化，保留字母数字和中文
    normalized = unicodedata.normalize("NFKC", name)
    # 非字母数字字符（含中文）替换为下划线
    agent_id = re.sub(r"[^\w\u4e00-\u9fff]", "_", normalized, flags=re.UNICODE)
    # 转小写
    agent_id = agent_id.lower()
    # 合并连续下划线
    agent_id = re.sub(r"_+", "_", agent_id)
    # 去除首尾下划线
    agent_id = agent_id.strip("_")
    return agent_id or "agent"


@agent_app.command("list")
def agent_list() -> None:
    """列出所有 Agent。"""
    asyncio.run(_list_agents())


async def _list_agents() -> None:
    """从 Backend 获取 Agent 列表。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            response = await client.get(
                "/api/v1/admin/agents",
                headers=headers,
                timeout=config.timeout,
            )
            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                console.print("[dim]可通过 XAGENT_ADMIN_TOKEN 环境变量设置[/dim]")
                return
            if response.status_code != 200:
                console.print(f"[red]获取 Agent 列表失败: {response.status_code}[/red]")
                return

            agents = response.json()
            if not isinstance(agents, list):
                agents = []

            table = Table(title="Agent 列表", show_header=True)
            table.add_column("Agent ID", style="cyan", max_width=36)
            table.add_column("名称", style="green")
            table.add_column("类型", style="yellow")

            for agent_item in agents:
                table.add_row(
                    agent_item.get("agent_id", ""),
                    agent_item.get("agent_name", ""),
                    agent_item.get("agent_type", ""),
                )

            console.print(table)
            console.print(f"[dim]共 {len(agents)} 个 Agent[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")


@agent_app.command("info")
def agent_info(
    agent_id: str = typer.Argument(help="Agent ID"),
) -> None:
    """查看 Agent 详情。"""
    asyncio.run(_get_agent_info(agent_id))


async def _get_agent_info(agent_id: str) -> None:
    """从 Backend 获取 Agent 详情。"""
    config = CLIConfig.from_env()
    try:
        async with httpx.AsyncClient(base_url=config.server_url) as client:
            headers = {"X-Admin-Token": config.admin_token}
            # 先获取所有 Agent，从中查找指定 ID
            response = await client.get(
                "/api/v1/admin/agents",
                headers=headers,
                timeout=config.timeout,
            )
            if response.status_code == 401:
                console.print("[red]认证失败：admin token 无效[/red]")
                return
            if response.status_code != 200:
                console.print(f"[red]获取 Agent 详情失败: {response.status_code}[/red]")
                return

            agents = response.json()
            matched = [a for a in agents if a.get("agent_id") == agent_id]

            if not matched:
                console.print(f"[yellow]Agent '{agent_id}' 未找到[/yellow]")
                return

            agent_data = matched[0]
            console.print(f"[bold]Agent ID:[/bold] {agent_data.get('agent_id', '')}")
            console.print(f"[bold]名称:[/bold] {agent_data.get('agent_name', '')}")
            console.print(f"[bold]类型:[/bold] {agent_data.get('agent_type', '')}")
            console.print(f"[bold]人设:[/bold] {agent_data.get('agent_persona', '(无)')}")
            console.print(f"[bold]用户 ID:[/bold] {agent_data.get('user_id', '')}")

    except httpx.ConnectError:
        console.print(f"[red]无法连接到 {config.server_url}[/red]")
