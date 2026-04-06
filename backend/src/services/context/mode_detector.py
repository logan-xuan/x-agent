"""Simple mode detector for stateful runtime compatibility tests."""

from __future__ import annotations


class ModeDetector:
    def detect(self, *, messages: list[dict], tools: list[dict] | None = None) -> str:
        text = " ".join(str(message.get("content", "")) for message in messages)
        tool_text = " ".join(str(tool.get("function", {}).get("name", "")) for tool in tools or [])
        merged = f"{text} {tool_text}"
        if any(keyword in merged for keyword in ["调研", "分析", "research", "web_search"]):
            return "research"
        if any(keyword in merged for keyword in ["撰写", "文档", "PRD", "write_file"]):
            return "writing"
        return "general"
