"""Runtime tool result normalization for prompt-safe history retention."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..runtime.types import ArtifactRef


@dataclass
class NormalizedToolResult:
    """Normalized representation of one tool result."""

    display_text: str
    archive_text: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeToolResultNormalizer:
    """Normalize noisy tool outputs into compact transcript-friendly summaries."""

    web_search_result_limit: int = 3
    web_search_snippet_chars: int = 160
    fetch_findings_chars: int = 240
    fetch_preview_chars: int = 280
    fetch_preview_chunk_lines: int = 120
    fetch_large_word_count: int = 1800
    fetch_large_line_count: int = 240
    fetch_near_budget_remaining_calls: int = 3
    fetch_near_budget_remaining_read_file_calls: int = 2
    fetch_budget_total_limit_fallback: int = 12
    fetch_budget_read_file_limit_fallback: int = 8
    terminal_head_chars: int = 1000
    terminal_tail_chars: int = 600
    file_head_chars: int = 1200
    file_tail_chars: int = 800

    def normalize(
        self,
        *,
        tool_name: str,
        output_text: str,
        details: dict[str, Any],
    ) -> NormalizedToolResult:
        raw_text = output_text or ""
        normalized_details = dict(details)
        normalized_details["raw_output_length"] = len(raw_text)

        if tool_name == "web_search":
            display_text = self._normalize_web_search(raw_text, normalized_details)
        elif tool_name == "fetch_web_content":
            display_text = self._normalize_fetch_web_content(raw_text, normalized_details)
        elif tool_name == "run_in_terminal":
            display_text = self._normalize_terminal(raw_text, normalized_details)
        elif tool_name == "read_file":
            display_text = self._normalize_read_file(raw_text, normalized_details)
        elif tool_name == "write_file":
            display_text = self._normalize_write_file(raw_text, normalized_details)
        else:
            display_text = raw_text

        normalized_details["normalized_output_length"] = len(display_text)
        normalized_details["normalized_tool_name"] = tool_name
        return NormalizedToolResult(
            display_text=display_text,
            archive_text=raw_text,
            details=normalized_details,
        )

    def attach_artifact_ref(
        self,
        *,
        tool_name: str,
        display_text: str,
        artifact_ref: ArtifactRef,
    ) -> str:
        artifact_line = f"Artifact: {artifact_ref.id}"
        if artifact_line in display_text:
            return display_text
        if display_text.startswith("["):
            return f"{display_text}\n{artifact_line}"
        return (
            f"[{tool_name}]\n"
            f"{display_text}\n"
            f"{artifact_line}"
        ).strip()

    def _normalize_web_search(self, output_text: str, details: dict[str, Any]) -> str:
        query = str(details.get("query") or "").strip()
        lines = [line.rstrip() for line in output_text.splitlines()]
        result_lines: list[str] = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^\d+\.\s+\*\*.*\*\*$", stripped):
                if len(result_lines) >= self.web_search_result_limit * 3:
                    break
                capture = True
                result_lines.append(stripped.replace("**", ""))
                continue
            if not capture:
                continue
            if not stripped:
                continue
            result_lines.append(self._trim_line(stripped, self.web_search_snippet_chars))
            if len(result_lines) >= self.web_search_result_limit * 3:
                break

        if not result_lines:
            result_lines.append(self._trim_line(output_text, self.web_search_snippet_chars))

        header = ["[web_search]"]
        if query:
            header.append(f"Query: {query}")
        return "\n".join([*header, *result_lines]).strip()

    def _normalize_fetch_web_content(self, output_text: str, details: dict[str, Any]) -> str:
        metadata = details.get("metadata", {}) if isinstance(details.get("metadata"), dict) else {}
        title = str(details.get("title") or "").strip()
        url = str(details.get("url") or details.get("final_url") or "").strip()
        markdown_path = str(metadata.get("markdown_path") or "").strip()
        word_count = details.get("word_count")
        body = str(details.get("body") or "").strip()
        preview_text = str(metadata.get("preview_text") or "").strip()
        line_count = self._as_int(metadata.get("line_count"))
        recommended_chunk_lines = (
            self._as_int(metadata.get("recommended_chunk_lines")) or self.fetch_preview_chunk_lines
        )
        preview_reasons = self._fetch_preview_reasons(details, line_count=line_count)
        details["fetch_preview_mode"] = bool(preview_reasons)
        if preview_reasons:
            details["fetch_preview_reasons"] = list(preview_reasons)
        lines = ["[fetch_web_content]"]
        if title:
            lines.append(f"Title: {title}")
        if url:
            lines.append(f"URL: {url}")
        if markdown_path:
            lines.append(f"Markdown: {markdown_path}")
        if word_count is not None:
            lines.append(f"Word count: {word_count}")
        if line_count is not None:
            lines.append(f"Lines: {line_count}")
        if preview_reasons:
            lines.append("Mode: preview")
            lines.append("Reason: " + "; ".join(preview_reasons))
            if preview_text:
                lines.append("Preview: " + self._trim_line(preview_text, self.fetch_preview_chars))
            if markdown_path:
                lines.append(
                    f'Next chunk: read_file(file_path="{markdown_path}", start_line=1, line_count={recommended_chunk_lines})'
                )
        if body and "[Markdown content saved to" not in body:
            lines.append("Summary: " + self._trim_line(body, self.fetch_findings_chars))
        return "\n".join(lines).strip()

    def _normalize_terminal(self, output_text: str, details: dict[str, Any]) -> str:
        if details.get("is_background") or details.get("process_id"):
            return self._normalize_background_terminal(output_text, details)

        returncode = details.get("returncode")
        stdout = ""
        stderr = ""
        if "STDERR:\n" in output_text:
            before, after = output_text.split("STDERR:\n", 1)
            stdout = before.removeprefix("STDOUT:\n").strip()
            stderr = after.strip()
        elif output_text.startswith("STDOUT:\n"):
            stdout = output_text.removeprefix("STDOUT:\n").strip()
        else:
            stdout = output_text.strip()

        lines = ["[run_in_terminal]"]
        if returncode is not None:
            lines.append(f"Return code: {returncode}")
        if stdout:
            lines.append("STDOUT:")
            lines.append(self._head_tail(stdout, self.terminal_head_chars, self.terminal_tail_chars))
        if stderr:
            lines.append("STDERR:")
            lines.append(self._head_tail(stderr, self.terminal_head_chars // 2, self.terminal_tail_chars // 2))
        return "\n".join(lines).strip()

    def _normalize_background_terminal(self, output_text: str, details: dict[str, Any]) -> str:
        process_id = str(details.get("process_id") or "").strip()
        command = str(details.get("command") or "").strip()
        working_dir = str(details.get("working_dir") or "").strip()
        title = str(details.get("background_task_title") or "").strip()
        completed = details.get("completed")
        returncode = details.get("returncode")

        lines = ["[run_in_terminal]"]
        if title:
            lines.append(f"Task: {title}")
        if process_id:
            lines.append(f"Process ID: {process_id}")
        if completed is False:
            lines.append("Status: running in background")
        elif completed is True:
            lines.append(
                "Status: completed"
                if returncode in {None, 0}
                else f"Status: failed (exit code: {returncode})"
            )
        if command:
            lines.append(f"Command: {command}")
        if working_dir:
            lines.append(f"Working dir: {working_dir}")
        if completed is False and process_id:
            lines.append(f'Progress: call get_terminal_output(process_id="{process_id}")')
        if output_text.strip():
            lines.append("")
            lines.append(self._head_tail(output_text.strip(), self.terminal_head_chars, self.terminal_tail_chars))
        return "\n".join(lines).strip()

    def _normalize_read_file(self, output_text: str, details: dict[str, Any]) -> str:
        file_path = str(details.get("file_path") or "").strip()
        size = details.get("size")
        start_line = self._as_int(details.get("start_line"))
        end_line = self._as_int(details.get("end_line"))
        total_lines = self._as_int(details.get("total_lines"))
        next_start_line = self._as_int(details.get("next_start_line"))
        line_count = self._as_int(details.get("line_count"))
        lines = ["[read_file]"]
        if file_path:
            lines.append(f"File: {file_path}")
        if size is not None:
            lines.append(f"Size: {size}")
        if start_line is not None and end_line is not None:
            if total_lines is not None:
                lines.append(f"Lines: {start_line}-{end_line} / {total_lines}")
            else:
                lines.append(f"Lines: {start_line}-{end_line}")
        if details.get("has_more") and file_path and next_start_line is not None and line_count is not None:
            lines.append(
                f'Next chunk: read_file(file_path="{file_path}", start_line={next_start_line}, line_count={line_count})'
            )
        lines.append(self._head_tail(output_text.strip(), self.file_head_chars, self.file_tail_chars))
        return "\n".join(lines).strip()

    def _normalize_write_file(self, output_text: str, details: dict[str, Any]) -> str:
        file_path = str(details.get("file_path") or "").strip()
        content_length = details.get("content_length")
        lines = ["[write_file]"]
        if file_path:
            lines.append(f"File: {file_path}")
        if content_length is not None:
            lines.append(f"Chars written: {content_length}")
        first_line = output_text.strip().splitlines()[0] if output_text.strip() else ""
        lines.append(self._trim_line(first_line, 180))
        return "\n".join(lines).strip()

    def _head_tail(self, value: str, head_chars: int, tail_chars: int) -> str:
        text = value.strip()
        if len(text) <= head_chars + tail_chars + 32:
            return text
        omitted = len(text) - head_chars - tail_chars
        return (
            f"{text[:head_chars]}\n"
            f"[... {omitted} chars omitted ...]\n"
            f"{text[-tail_chars:]}"
        )

    def _trim_line(self, value: str, max_chars: int) -> str:
        line = " ".join(value.split())
        if len(line) <= max_chars:
            return line
        return f"{line[: max_chars - 3]}..."

    def _fetch_preview_reasons(self, details: dict[str, Any], *, line_count: int | None) -> list[str]:
        reasons: list[str] = []
        word_count = self._as_int(details.get("word_count"))
        if word_count is not None and word_count >= self.fetch_large_word_count:
            reasons.append("large page")
        if line_count is not None and line_count >= self.fetch_large_line_count:
            reasons.append("long markdown")

        total_calls = self._as_int(details.get("tool_budget_total_calls"))
        if total_calls is not None:
            max_total_calls = self._resolve_limit(
                details.get("tool_budget_max_total_calls"),
                self.fetch_budget_total_limit_fallback,
            )
            if (
                max_total_calls is not None
                and max_total_calls > 0
                and max_total_calls - total_calls <= self.fetch_near_budget_remaining_calls
            ):
                reasons.append("tool budget nearly exhausted")

        per_tool_calls = (
            details.get("tool_budget_per_tool_calls")
            if isinstance(details.get("tool_budget_per_tool_calls"), dict)
            else {}
        )
        max_calls_by_name = (
            details.get("tool_budget_max_calls_by_name")
            if isinstance(details.get("tool_budget_max_calls_by_name"), dict)
            else {}
        )
        read_file_calls = self._as_int(per_tool_calls.get("read_file"))
        if read_file_calls is not None:
            read_file_limit = self._resolve_limit(
                max_calls_by_name.get("read_file"),
                self.fetch_budget_read_file_limit_fallback,
            )
            if (
                read_file_limit is not None
                and read_file_limit > 0
                and read_file_limit - read_file_calls
                <= self.fetch_near_budget_remaining_read_file_calls
            ):
                reasons.append("read_file budget nearly exhausted")
        return reasons

    def _as_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    def _resolve_limit(self, value: Any, fallback: int) -> int | None:
        resolved = self._as_int(value)
        if resolved is not None:
            return resolved
        return fallback
