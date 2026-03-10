"""CLI chat 命令 — 对话功能。

支持交互式对话和单次对话两种模式：
- x-agent chat              → 进入交互式对话
- x-agent chat "你好"        → 单次对话并退出

可选参数：
- --session / -s: 指定会话 ID
- --new / -n: 强制新建会话
- --agent / -a: 指定 Agent 名称
- --agent-id: 指定 Agent ID
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import typer
from rich.console import Console

from ..config import CLIConfig

chat_app = typer.Typer(invoke_without_command=True)
console = Console()


@chat_app.callback(invoke_without_command=True)
def chat(
    message: Optional[str] = typer.Argument(None, help="单次对话消息，不传则进入交互模式"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="会话 ID"),
    new: bool = typer.Option(False, "--new", "-n", help="强制新建会话"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent 名称"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", help="Agent ID"),
) -> None:
    """与 Agent 对话。

    不传参数进入交互式对话模式，传入消息则为单次对话。
    """
    config = CLIConfig.from_env()
    session_id = None if new else (session or config.default_session_id or str(uuid.uuid4()))

    if message:
        asyncio.run(_single_chat(config, message, session_id, agent, agent_id))
    else:
        asyncio.run(_interactive_chat(config, session_id, agent, agent_id))


async def _single_chat(
    config: CLIConfig,
    message: str,
    session_id: str | None,
    agent_name: str | None,
    agent_id: str | None,
) -> None:
    """单次对话模式。"""
    from ..adapters.gateway_client import GatewayClient
    from ..adapters.output_renderer import OutputRenderer

    effective_session_id = session_id or str(uuid.uuid4())
    client = GatewayClient(config)
    renderer = OutputRenderer(config, console)

    try:
        async for event in client.chat(
            content=message,
            session_id=effective_session_id,
            agent_name=agent_name,
            agent_id=agent_id,
        ):
            renderer.render_event(event)
    except Exception as error:
        console.print(f"[red]Error: {error}[/red]")
        raise typer.Exit(code=1)
    finally:
        renderer.finalize()
        await client.close()


async def _interactive_chat(
    config: CLIConfig,
    session_id: str | None,
    agent_name: str | None,
    agent_id: str | None,
) -> None:
    """交互式对话模式。"""
    from ..adapters.gateway_client import GatewayClient
    from ..adapters.output_renderer import OutputRenderer

    effective_session_id = session_id or str(uuid.uuid4())
    client = GatewayClient(config)
    renderer = OutputRenderer(config, console)

    console.print("[bold green]X-Agent 交互式对话[/bold green]")
    console.print(f"[dim]Session: {effective_session_id}[/dim]")
    console.print("[dim]输入 /quit 或 Ctrl+C 退出[/dim]\n")

    try:
        while True:
            try:
                user_input = console.input("[bold blue]你> [/bold blue]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]再见！[/dim]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.lower() in ("/quit", "/exit", "/q"):
                console.print("[dim]再见！[/dim]")
                break

            console.print()
            try:
                async for event in client.chat(
                    content=user_input,
                    session_id=effective_session_id,
                    agent_name=agent_name,
                    agent_id=agent_id,
                ):
                    renderer.render_event(event)
            except Exception as error:
                console.print(f"[red]Error: {error}[/red]")

            renderer.finalize()
            console.print()
    finally:
        await client.close()
