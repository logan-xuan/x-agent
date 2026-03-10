"""终端输出渲染器。

使用 Rich 库将 GatewaySSEEvent 渲染为美观的终端输出：
- 文本流式输出（逐字显示）
- 思考过程（灰色斜体，可配置显示/隐藏）
- 工具调用（折叠显示工具名和参数）
- 错误信息（红色高亮）
- 消息完成（显示模型信息）
"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from ..config import CLIConfig
from .gateway_client import GatewaySSEEvent


class OutputRenderer:
    """终端输出渲染器。

    将 GatewaySSEEvent 流式渲染到终端，
    支持 Markdown 格式化、工具调用折叠等。

    用法::

        renderer = OutputRenderer(config, console)
        for event in events:
            renderer.render_event(event)
        renderer.finalize()
    """

    def __init__(self, config: CLIConfig, console: Console) -> None:
        self._config = config
        self._console = console
        self._accumulated_text = ""
        self._in_thinking = False
        self._thinking_text = ""

    def render_event(self, event: GatewaySSEEvent) -> None:
        """渲染单个事件。

        Args:
            event: Gateway SSE 事件。
        """
        if event.is_done:
            return

        handler = _EVENT_HANDLERS.get(event.event_type)
        if handler:
            handler(self, event)

    def finalize(self) -> None:
        """完成当前消息的渲染。

        输出累积的文本（Markdown 格式化），
        并重置内部状态。
        """
        if self._in_thinking and self._thinking_text:
            self._console.print(
                f"[dim italic]{self._thinking_text}[/dim italic]",
                end="",
            )
            self._thinking_text = ""
            self._in_thinking = False

        if self._accumulated_text:
            self._console.print()
            self._accumulated_text = ""

    def _handle_text_chunk(self, event: GatewaySSEEvent) -> None:
        """处理文本片段事件。"""
        content = event.data.get("content", "")
        if content:
            self._accumulated_text += content
            self._console.print(content, end="", highlight=False)

    def _handle_thinking_chunk(self, event: GatewaySSEEvent) -> None:
        """处理思考过程片段。"""
        if not self._config.show_thinking:
            return

        content = event.data.get("content", "")
        if content:
            if not self._in_thinking:
                self._in_thinking = True
                self._console.print("[dim italic]", end="")
            self._thinking_text += content
            self._console.print(content, end="", highlight=False)

    def _handle_message_end(self, event: GatewaySSEEvent) -> None:
        """处理消息完成事件。"""
        if self._in_thinking:
            self._console.print("[/dim italic]")
            self._in_thinking = False
            self._thinking_text = ""

        model = event.data.get("model", "")
        if model:
            self._console.print(f"\n[dim]({model})[/dim]")

    def _handle_tool_call(self, event: GatewaySSEEvent) -> None:
        """处理工具调用事件。"""
        if not self._config.show_tool_calls:
            return

        tool_name = event.data.get("name", "unknown")
        self._console.print(f"\n[yellow]🔧 调用工具: {tool_name}[/yellow]")

    def _handle_tool_result(self, event: GatewaySSEEvent) -> None:
        """处理工具结果事件。"""
        if not self._config.show_tool_calls:
            return

        is_error = event.data.get("is_error", False)
        if is_error:
            error_msg = event.data.get("result", "")
            self._console.print(f"[red]  ✗ 工具执行失败: {error_msg}[/red]")
        else:
            self._console.print("[green]  ✓ 工具执行完成[/green]")

    def _handle_error(self, event: GatewaySSEEvent) -> None:
        """处理错误事件。"""
        message = event.data.get("message", "Unknown error")
        self._console.print(f"\n[red bold]Error: {message}[/red bold]")

    def _handle_agent_start(self, event: GatewaySSEEvent) -> None:
        """处理 Agent 开始事件。"""
        agent_name = event.agent_name or event.data.get("agent_name", "")
        if agent_name:
            self._console.print(f"[dim]Agent: {agent_name}[/dim]")

    def _handle_agent_end(self, event: GatewaySSEEvent) -> None:
        """处理 Agent 结束事件（静默）。"""


# 事件类型 → 处理方法映射
_EVENT_HANDLERS: dict[str, Callable[[OutputRenderer, GatewaySSEEvent], None]] = {
    "text_chunk": OutputRenderer._handle_text_chunk,
    "thinking_chunk": OutputRenderer._handle_thinking_chunk,
    "message_end": OutputRenderer._handle_message_end,
    "tool_call": OutputRenderer._handle_tool_call,
    "tool_result": OutputRenderer._handle_tool_result,
    "error": OutputRenderer._handle_error,
    "agent_start": OutputRenderer._handle_agent_start,
    "agent_end": OutputRenderer._handle_agent_end,
}
