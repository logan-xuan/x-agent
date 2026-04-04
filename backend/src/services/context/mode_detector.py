"""Lightweight task mode detection for context assembly."""

from __future__ import annotations

from typing import Any


class ModeDetector:
    """Infer a coarse-grained task mode from the latest conversation state."""

    _RESEARCH_KEYWORDS = ("调研", "研究", "竞品", "市场", "分析", "research")
    _WRITING_KEYWORDS = ("prd", "文档", "方案", "报告", "撰写", "write")
    _CODING_KEYWORDS = ("代码", "bug", "调试", "实现", "测试", "重构", "code")

    def detect(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Detect task mode from recent user-visible messages and tools."""
        recent_text = "\n".join(
            str(msg.get("content", ""))
            for msg in messages[-6:]
            if msg.get("role") in {"user", "assistant"}
        ).lower()

        if any(keyword in recent_text for keyword in self._RESEARCH_KEYWORDS):
            return "research"
        if any(keyword in recent_text for keyword in self._WRITING_KEYWORDS):
            return "writing"
        if any(keyword in recent_text for keyword in self._CODING_KEYWORDS):
            return "coding"

        tool_names = {
            _tool_name(tool).lower()
            for tool in (tools or [])
            if _tool_name(tool)
        }
        if {"web_search", "fetch_web_content"} & tool_names:
            return "research"
        if {"write_file", "append_file", "edit_file"} & tool_names:
            return "writing"
        if {"run_in_terminal"} & tool_names:
            return "coding"

        return "chat"


def get_mode_detector() -> ModeDetector:
    return ModeDetector()


def _tool_name(tool: dict[str, Any]) -> str:
    if not tool:
        return ""
    if hasattr(tool, "name"):
        return str(getattr(tool, "name") or "")
    if "tool_name" in tool:
        return str(tool.get("tool_name") or "")
    if tool.get("type") == "function":
        function = tool.get("function") or {}
        return str(function.get("name") or "")
    return ""
