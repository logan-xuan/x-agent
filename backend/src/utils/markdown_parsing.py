"""Helpers for extracting lightweight metadata from Markdown files."""

from __future__ import annotations

import re
from collections.abc import Sequence


def extract_markdown_field(content: str, aliases: Sequence[str]) -> str:
    """Extract an inline or section-style field value by trying multiple aliases."""
    for alias in aliases:
        value = _extract_single_field(content, alias)
        if value:
            return value
    return ""


def extract_markdown_section(content: str, aliases: Sequence[str]) -> str:
    """Extract a section body under any matching Markdown heading alias."""
    for alias in aliases:
        pattern = re.compile(
            rf"(?ms)^##+\s*{re.escape(alias)}\s*$\n(.*?)(?=^##+\s+\S|\Z)"
        )
        match = pattern.search(content)
        if match:
            section = match.group(1).strip()
            if section:
                return section
    return ""


def parse_markdown_list_items(content: str) -> list[str]:
    """Parse bullet or numbered list items from Markdown content."""
    items: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"^[-*+]\s+", line):
            line = re.sub(r"^[-*+]\s+", "", line)
        elif re.match(r"^\d+[\.\)]\s+", line):
            line = re.sub(r"^\d+[\.\)]\s+", "", line)
        else:
            continue

        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line).strip()
        if line:
            items.append(line)

    return items


def parse_markdown_key_values(content: str) -> dict[str, str]:
    """Parse simple key-value lines from Markdown content."""
    result: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\*\*(.*?)\*\*$", r"\1", line)

        if "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue

        key = re.sub(r"^\*\*(.*?)\*\*$", r"\1", key.strip()).strip()
        value = re.sub(r"\*\*(.*?)\*\*", r"\1", value.strip()).strip()
        if key and value:
            result[key] = value

    return result


def _extract_single_field(content: str, alias: str) -> str:
    escaped = re.escape(alias)
    patterns = [
        re.compile(rf"(?m)^[ \t>*-]*\*\*{escaped}:\*\*\s*(.+?)\s*$"),
        re.compile(rf"(?m)^[ \t>*-]*\*\*{escaped}\*\*:\s*(.+?)\s*$"),
        re.compile(rf"(?m)^[ \t>*-]*{escaped}[：:]\s*(.+?)\s*$"),
        re.compile(rf"(?ms)^##+\s*{escaped}\s*$\n(.*?)(?=^##+\s+\S|\Z)"),
    ]

    for pattern in patterns:
        match = pattern.search(content)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    return ""
