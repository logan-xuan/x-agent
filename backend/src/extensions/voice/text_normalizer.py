"""Utilities for turning rich markdown-ish replies into speech-friendly text."""

from __future__ import annotations

import re
from html import unescape

_TTS_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_REFERENCE_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_REFERENCE_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\[[^\]]*\]")
_INLINE_CODE_RE = re.compile(r"`{1,3}([^`]*)`{1,3}")
_STRONG_RE = re.compile(r"(\*\*|__)([\s\S]+?)\1")
_EMPHASIS_RE = re.compile(r"(?<!\w)(\*|_)([^*_]+?)\1(?!\w)")
_STRIKETHROUGH_RE = re.compile(r"~~([\s\S]+?)~~")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BREAK_RE = re.compile(r"<\s*(?:br|/p|/div|/li|/tr)\s*/?\s*>", flags=re.IGNORECASE)
_REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+\]:\s+\S+.*$", flags=re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INDENTED_CODE_RE = re.compile(r"(?m)(?:^(?: {4}|\t).*(?:\n|$))+")
_ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s+")
_UNORDERED_LIST_RE = re.compile(r"^[-*+]\s+")
_TASK_LIST_RE = re.compile(r"^(?:[-*+]\s+)?\[[ xX]\]\s+")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_BLOCKQUOTE_RE = re.compile(r"^>+\s*")
_AUTOLINK_RE = re.compile(r"<(https?://[^>]+)>")
_BARE_URL_RE = re.compile(r"https?://[^\s)]+")
_HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|?$")
_WHITESPACE_RE = re.compile(r"\s+")

_SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", "；", ";", "：", ":")
_STRUCTURED_LINE_TYPES = {"heading", "blockquote", "list", "image", "table"}


def normalize_text_for_tts(text: str) -> str:
    """Convert markdown-ish rich text into speech-friendly plain text."""
    normalized = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = _HTML_BREAK_RE.sub("\n", normalized)
    normalized = _REFERENCE_LINK_RE.sub("", normalized)
    normalized = _CODE_FENCE_RE.sub("\n代码片段已省略。\n", normalized)
    normalized = _INDENTED_CODE_RE.sub("\n代码片段已省略。\n", normalized)
    normalized = _HTML_TAG_RE.sub(" ", normalized)

    spoken_lines: list[tuple[str, str]] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line or _HORIZONTAL_RULE_RE.match(line) or _TABLE_SEPARATOR_RE.match(line):
            continue

        line_type = "paragraph"
        if raw_line.strip().startswith("!["):
            line_type = "image"
        elif _HEADING_RE.match(line):
            line_type = "heading"
        elif _BLOCKQUOTE_RE.match(line):
            line_type = "blockquote"
        elif _TASK_LIST_RE.match(line) or _UNORDERED_LIST_RE.match(line) or _ORDERED_LIST_RE.match(line):
            line_type = "list"

        task_match = _TASK_LIST_RE.match(line)
        ordered_match = _ORDERED_LIST_RE.match(line)

        prefix = ""
        if task_match:
            marker = task_match.group(0).lower()
            prefix = "已完成 " if "[x]" in marker else "待办 "
        elif ordered_match:
            number_token = ordered_match.group(0).split(".", 1)[0].split(")", 1)[0]
            prefix = f"第{number_token}项 "

        line = _HEADING_RE.sub("", line)
        line = _BLOCKQUOTE_RE.sub("", line)
        line = _TASK_LIST_RE.sub("", line)
        line = _UNORDERED_LIST_RE.sub("", line)
        line = _ORDERED_LIST_RE.sub("", line)

        table_match = _TABLE_ROW_RE.match(line)
        if table_match:
            line_type = "table"
            cells = [
                _clean_inline_text(cell)
                for cell in table_match.group(1).split("|")
                if _clean_inline_text(cell)
            ]
            line = "，".join(cells)
        else:
            line = _clean_inline_text(line)

        if not line:
            continue

        line = f"{prefix}{line}".strip()
        spoken_lines.append((line, line_type))

    rendered_lines: list[str] = []
    for index, (line, line_type) in enumerate(spoken_lines):
        has_next = index < len(spoken_lines) - 1
        if (
            has_next
            and line_type in _STRUCTURED_LINE_TYPES
            and not line.endswith(_SENTENCE_ENDINGS)
        ):
            rendered_lines.append(f"{line}。")
        else:
            rendered_lines.append(line)

    return " ".join(rendered_lines).strip()


def plain_text_fallback_for_tts(text: str) -> str:
    """Return a punctuation-light fallback string for engines with fragile parsers."""
    plain = normalize_text_for_tts(text)
    plain = re.sub(r"[^\w\u4e00-\u9fff]+", " ", plain, flags=re.UNICODE)
    plain = _WHITESPACE_RE.sub(" ", plain).strip()
    return plain


def _clean_inline_text(text: str) -> str:
    normalized = text
    normalized = _MARKDOWN_IMAGE_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _MARKDOWN_LINK_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _REFERENCE_MARKDOWN_IMAGE_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _REFERENCE_MARKDOWN_LINK_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _INLINE_CODE_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _STRONG_RE.sub(lambda match: match.group(2).strip(), normalized)
    normalized = _STRIKETHROUGH_RE.sub(lambda match: match.group(1).strip(), normalized)
    normalized = _EMPHASIS_RE.sub(lambda match: match.group(2).strip(), normalized)
    normalized = _AUTOLINK_RE.sub("", normalized)
    normalized = _BARE_URL_RE.sub("", normalized)
    normalized = _TTS_EMOJI_PATTERN.sub(" ", normalized)
    normalized = normalized.replace("\uFE0F", " ")
    normalized = normalized.replace("°C", "摄氏度")
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)
    normalized = re.sub(r"\s+([，。！？；：])", r"\1", normalized)
    return normalized
