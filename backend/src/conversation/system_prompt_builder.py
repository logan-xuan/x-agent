"""系统提示词构建器.

从 workspace 动态加载 Bootstrap 文件（AGENTS.md、SPIRIT.md、TOOLS.md 等），
以 Project Context 的形式注入到 system prompt 末尾。
实现 agent_core 的 SystemPromptPort 接口。

职责:
    - 启动时检测 workspace，首次使用时从模板目录初始化文件
    - 按固定顺序加载 Bootstrap 文件（AGENTS.md 优先级最高）
    - BOOTSTRAP.md 仅在全新 workspace 时创建
    - SPIRIT.md 存在时注入特殊人格指令
    - 单文件最大 20K / 总计最大 150K 截断保护
    - 缺失文件标记为 [MISSING]
    - 组装核心提示词 + Project Context
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.manager import ConfigManager
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..agent_core.ports.system_prompt_port import IdentityInfo

logger = get_logger(__name__)

# ─── 常量 ───

# Bootstrap 文件加载顺序（决定优先级）
BOOTSTRAP_FILE_ORDER: list[str] = [
    "AGENTS.md",
    "SPIRIT.md",
    "TOOLS.md",
    "IDENTITY.md",
    "OWNER.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "MEMORY.md",
]

# 截断限制
MAX_SINGLE_FILE_CHARS: int = 20_000
MAX_TOTAL_CHARS: int = 150_000

# 模板目录（相对于本文件）
_TEMPLATE_DIR: Path = Path(__file__).parent.parent / "docs" / "bootstrap"

# 英文星期到中文的映射
_WEEKDAY_MAP: dict[str, str] = {
    "Monday": "星期一",
    "Tuesday": "星期二",
    "Wednesday": "星期三",
    "Thursday": "星期四",
    "Friday": "星期五",
    "Saturday": "星期六",
    "Sunday": "星期日",
}

# Skills 注入占位标记（websocket.py 动态替换为实际 Skills 内容）
SKILLS_INJECTION_MARKER: str = "<!-- SKILLS_INJECTION_POINT -->"

# 默认系统提示词（当所有文件都不存在时使用）
_DEFAULT_SYSTEM_PROMPT: str = """You are a personal assistant running inside x-agent.

# 重要
- 请使用中文回复用户
- 简洁明了地回答问题
- 需要时可以使用工具获取信息
- 如果不确定，坦诚告知用户"""

# SPIRIT.md 存在时注入的特殊指令
_SPIRIT_PERSONA_INSTRUCTION: str = (
    "If SPIRIT.md is present, embody its persona and tone. "
    "Avoid stiff, generic replies."
)


@dataclass
class ContextFile:
    """一个已加载的 Bootstrap 上下文文件.

    Attributes:
        path: 文件完整路径
        filename: 文件名（如 AGENTS.md）
        content: 文件内容（可能被截断）
        is_missing: 文件是否缺失
        is_truncated: 内容是否被截断
    """

    path: str
    filename: str
    content: str
    is_missing: bool = False
    is_truncated: bool = False


class SystemPromptBuilder:
    """系统提示词构建器.

    启动时从 workspace 目录加载 Bootstrap 文件，以 Project Context 形式
    注入到 system prompt 末尾。实现 SystemPromptPort 接口。

    Attributes:
        workspace_path: workspace 目录路径
    """

    def __init__(self, workspace_path: str | None = None) -> None:
        """初始化构建器.

        读取 workspace 路径，执行首次初始化检查（从模板复制缺失文件）。

        Args:
            workspace_path: workspace 目录路径。
                如果为 None，从 ConfigManager 读取配置。
        """
        if workspace_path is not None:
            self.workspace_path = str(Path(workspace_path).expanduser())
        else:
            config = ConfigManager().config
            raw_path = config.workspace.path if config.workspace else "workspace"
            self.workspace_path = str(Path(raw_path).expanduser())

        self._template_dir = _TEMPLATE_DIR
        self._ensure_workspace_initialized()

        logger.info(
            "SystemPromptBuilder initialized",
            extra={"workspace_path": self.workspace_path},
        )

    # ─── 公开接口（实现 SystemPromptPort）───

    def build_system_prompt(self) -> str:
        """构建完整的系统提示词.

        两种模式：
        - 未出生模式：BOOTSTRAP.md 作为最高优先级核心指令，引导 Agent 完成初始化
        - 已出生模式：核心提示词 + Project Context（Bootstrap 文件原文注入）

        Returns:
            组装好的系统提示词字符串
        """
        try:
            agent_born = self._is_agent_born()

            # 未出生模式：BOOTSTRAP.md 作为核心指令
            if not agent_born:
                bootstrap_prompt = self._build_bootstrap_prompt()
                if bootstrap_prompt:
                    logger.info("Agent not born yet, using bootstrap prompt as primary instruction")
                    return bootstrap_prompt

            # 已出生模式：正常构建
            core_prompt = self._build_core_prompt()
            context_files = self._load_context_files()

            valid_files = [cf for cf in context_files if not cf.is_missing]
            if not valid_files:
                logger.warning("No bootstrap files found, using default prompt")
                return _DEFAULT_SYSTEM_PROMPT

            project_context = self._build_project_context(context_files)
            return f"{core_prompt}\n\n{project_context}"

        except Exception as error:
            logger.warning(
                "Failed to build system prompt",
                extra={"error": str(error)},
            )
            return _DEFAULT_SYSTEM_PROMPT

    def load_identity(self) -> "IdentityInfo":
        """加载 AI 身份信息.

        解析 IDENTITY.md 文件，提取 name、form、style、emoji。
        保持向后兼容。

        Returns:
            IdentityInfo 数据对象
        """
        from ..agent_core.ports.system_prompt_port import IdentityInfo

        identity_path = Path(self.workspace_path) / "IDENTITY.md"
        if not identity_path.exists():
            return IdentityInfo()

        try:
            content = identity_path.read_text(encoding="utf-8")
            return IdentityInfo(
                name=_extract_field(content, "Name"),
                form=_extract_field(content, "Creature"),
                style=_extract_field(content, "Vibe"),
                emoji=_extract_field(content, "Emoji"),
            )
        except Exception as error:
            logger.warning(
                "Failed to parse IDENTITY.md",
                extra={"error": str(error)},
            )
            return IdentityInfo()

    # ─── Workspace 初始化 ───

    def _ensure_workspace_initialized(self) -> None:
        """确保 workspace 已初始化.

        - workspace 目录不存在时自动创建
        - 全新 workspace：复制所有模板（含 BOOTSTRAP.md）
        - 非全新 workspace：仅复制缺失文件（不含 BOOTSTRAP.md）
        """
        workspace_dir = Path(self.workspace_path)

        if not workspace_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Created workspace directory",
                extra={"path": self.workspace_path},
            )

        if not self._template_dir.exists():
            logger.warning(
                "Template directory not found, skipping initialization",
                extra={"template_dir": str(self._template_dir)},
            )
            return

        is_fresh = self._is_fresh_workspace()

        for filename in BOOTSTRAP_FILE_ORDER:
            target_path = workspace_dir / filename
            if target_path.exists():
                continue

            # BOOTSTRAP.md 仅在全新 workspace 时创建
            if filename == "BOOTSTRAP.md" and not is_fresh:
                continue

            self._copy_template(filename)

        if is_fresh:
            logger.info("Fresh workspace initialized with all templates")
        else:
            logger.debug("Workspace initialization check completed")

    def _is_fresh_workspace(self) -> bool:
        """判断是否为全新 workspace.

        标准：workspace 目录下不存在任何 Bootstrap 文件。

        Returns:
            True 表示全新 workspace
        """
        workspace_dir = Path(self.workspace_path)
        return not any(
            (workspace_dir / filename).exists()
            for filename in BOOTSTRAP_FILE_ORDER
        )

    def _copy_template(self, filename: str) -> None:
        """从模板目录复制文件到 workspace.

        Args:
            filename: 要复制的文件名（如 AGENTS.md）
        """
        source_path = self._template_dir / filename
        target_path = Path(self.workspace_path) / filename

        if not source_path.exists():
            logger.debug(
                "Template file not found, skipping",
                extra={"filename": filename},
            )
            return

        try:
            shutil.copy2(str(source_path), str(target_path))
            logger.info(
                "Copied template to workspace",
                extra={"filename": filename, "target": str(target_path)},
            )
        except OSError as error:
            logger.warning(
                "Failed to copy template",
                extra={"filename": filename, "error": str(error)},
            )

    # ─── 文件加载 ───

    def _is_agent_born(self) -> bool:
        """判断 Agent 是否已完成初始化（"出生"）.

        标准：IDENTITY.md 存在且有实际内容（非空白）。

        Returns:
            True 表示 Agent 已出生，不再需要 BOOTSTRAP.md
        """
        identity_path = Path(self.workspace_path) / "IDENTITY.md"
        if not identity_path.exists():
            return False
        try:
            content = identity_path.read_text(encoding="utf-8").strip()
            return len(content) > 0
        except Exception:
            return False

    def _load_context_files(self) -> list[ContextFile]:
        """按固定顺序加载所有 Bootstrap 文件.

        应用单文件截断和总字符数截断保护。
        如果 Agent 已完成初始化，跳过 BOOTSTRAP.md 以节省 token。

        Returns:
            ContextFile 列表
        """
        context_files: list[ContextFile] = []
        total_chars = 0
        agent_born = self._is_agent_born()

        for filename in BOOTSTRAP_FILE_ORDER:
            # Agent 已出生后，跳过 BOOTSTRAP.md
            if filename == "BOOTSTRAP.md" and agent_born:
                logger.debug("Skipping BOOTSTRAP.md — agent already initialized")
                continue
            context_file = self._load_single_file(filename)

            if not context_file.is_missing:
                remaining_budget = MAX_TOTAL_CHARS - total_chars
                if remaining_budget <= 0:
                    context_file = ContextFile(
                        path=context_file.path,
                        filename=filename,
                        content="[TRUNCATED - total context limit reached]",
                        is_truncated=True,
                    )
                else:
                    content_len = len(context_file.content)
                    if total_chars + content_len > MAX_TOTAL_CHARS:
                        allowed = remaining_budget
                        context_file.content, _ = _truncate_content(
                            context_file.content, allowed
                        )
                        context_file.is_truncated = True

                total_chars += len(context_file.content)

            context_files.append(context_file)

        logger.info(
            "Context files loaded",
            extra={
                "total_files": len(context_files),
                "valid_files": sum(1 for cf in context_files if not cf.is_missing),
                "total_chars": total_chars,
            },
        )

        return context_files

    def _load_single_file(self, filename: str) -> ContextFile:
        """加载单个 Bootstrap 文件.

        处理文件缺失和单文件截断。

        Args:
            filename: 文件名（如 AGENTS.md）

        Returns:
            ContextFile 实例
        """
        file_path = Path(self.workspace_path) / filename
        full_path = str(file_path)

        if not file_path.exists():
            return ContextFile(
                path=full_path,
                filename=filename,
                content=f"[MISSING] Expected at: {full_path}",
                is_missing=True,
            )

        try:
            raw_content = file_path.read_text(encoding="utf-8", errors="replace")
            keep_tail = filename == "MEMORY.md"
            content, is_truncated = _truncate_content(
                raw_content, MAX_SINGLE_FILE_CHARS, keep_tail=keep_tail,
            )

            if is_truncated:
                logger.info(
                    "File content truncated",
                    extra={
                        "filename": filename,
                        "original_size": len(raw_content),
                        "truncated_size": len(content),
                    },
                )

            return ContextFile(
                path=full_path,
                filename=filename,
                content=content,
                is_truncated=is_truncated,
            )

        except Exception as error:
            logger.warning(
                "Failed to read bootstrap file",
                extra={"filename": filename, "error": str(error)},
            )
            return ContextFile(
                path=full_path,
                filename=filename,
                content=f"[MISSING] Expected at: {full_path}",
                is_missing=True,
            )

    # ─── Prompt 构建 ───

    def _build_bootstrap_prompt(self) -> str | None:
        """构建首次启动引导提示词.

        当 Agent 未出生时，将 BOOTSTRAP.md 的内容作为最高优先级的核心指令，
        确保 LLM 遵循引导流程（问用户名字、定义身份等），而不是回退到通用助手模式。

        Returns:
            引导提示词字符串，如果 BOOTSTRAP.md 不存在则返回 None
        """
        bootstrap_path = Path(self.workspace_path) / "BOOTSTRAP.md"
        if not bootstrap_path.exists():
            return None

        try:
            bootstrap_content = bootstrap_path.read_text(encoding="utf-8").strip()
            if not bootstrap_content:
                return None
        except Exception as error:
            logger.warning(
                "Failed to read BOOTSTRAP.md",
                extra={"error": str(error)},
            )
            return None

        # 构建以 BOOTSTRAP.md 为核心的 system prompt
        # 将引导指令放在最前面，确保最高优先级
        parts = [
            "# 首次启动引导（最高优先级）",
            "",
            "你尚未完成初始化。以下是你的出生引导，你必须严格遵循这些指引，"
            "与用户对话来完成初始化。不要像普通助手一样回复，不要说「有什么可以帮你的」。",
            "",
            bootstrap_content,
            "",
            "---",
            "",
            "# 重要",
            "- 请使用中文回复用户",
            "- 你可以使用 write_file 工具来创建或更新 IDENTITY.md、OWNER.md、SPIRIT.md 等文件",
            "",
            f"{SKILLS_INJECTION_MARKER}",
            "",
            f"# 当前时间\n{self._format_current_time()}",
        ]

        logger.info(
            "Bootstrap prompt built",
            extra={"bootstrap_content_length": len(bootstrap_content)},
        )

        return "\n".join(parts)

    def _build_core_prompt(self) -> str:
        """构建核心系统提示词.

        输出顺序:
        1. 角色声明
        2. 重要指令（语言要求）
        3. 运行时上下文（session_id / agent_id / channel_id）
        4. Skills 占位标记（由 websocket.py 动态替换）
        5. 当前时间

        Returns:
            核心提示词字符串
        """
        runtime_context = self._build_runtime_context()
        return (
            f"You are a personal assistant running inside x-agent.\n\n"
            f"# 重要\n- 请使用中文回复用户\n\n"
            f"{runtime_context}"
            f"{SKILLS_INJECTION_MARKER}\n\n"
            f"# 当前时间\n{self._format_current_time()}"
        )

    def _build_runtime_context(self) -> str:
        """构建运行时上下文信息块，注入到 system prompt 中.

        从当前请求的 AgentContext（contextvars）读取 session_id、agent_id、
        channel_id 等运行时参数，以结构化文本注入到 system prompt，
        使 LLM 在调用工具时能直接获取这些参数，无需调用方硬编码。

        Returns:
            运行时上下文字符串（含尾部换行），未获取到上下文时返回空字符串。
        """
        try:
            from .context import get_current_context

            context = get_current_context()
            if context is None:
                return ""

            identity = context.identity
            lines = ["# 运行时上下文（Runtime Context）", ""]
            lines.append("以下是当前会话的运行时参数，调用工具时可直接使用：")
            lines.append("")

            if identity.agent_id:
                lines.append(f"- **agent_id**: `{identity.agent_id}`")
            if identity.session_id:
                lines.append(f"- **session_id**: `{identity.session_id}`")
            if identity.channel_id:
                lines.append(f"- **channel_id**: `{identity.channel_id}`")
            if identity.channel_type:
                lines.append(f"- **channel_type**: `{identity.channel_type.value}`")

            lines.append("")
            return "\n".join(lines) + "\n\n"

        except Exception as exc:
            logger.debug(
                "Failed to build runtime context, skipping",
                extra={"error": str(exc)},
            )
            return ""

    def _build_project_context(self, context_files: list[ContextFile]) -> str:
        """将 Bootstrap 文件拼接为 Project Context 区块.

        格式参考 OpenClaw：
        - 以 `# Project Context` 一级标题引入
        - SPIRIT.md 存在时注入特殊人格指令
        - 每个文件用 `## <文件完整路径>` 作为标题

        Args:
            context_files: 已加载的 ContextFile 列表

        Returns:
            Project Context 区块字符串
        """
        lines: list[str] = [
            "# Project Context",
            "",
            "The following project context files have been loaded:",
        ]

        # SPIRIT.md 特殊处理
        has_spirit = any(
            cf.filename == "SPIRIT.md" and not cf.is_missing
            for cf in context_files
        )
        if has_spirit:
            lines.append(_SPIRIT_PERSONA_INSTRUCTION)

        lines.append("")

        for context_file in context_files:
            lines.append(f"## {context_file.path}")
            lines.append("")
            lines.append(context_file.content)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_current_time() -> str:
        """格式化当前时间为中文字符串.

        Returns:
            格式化后的时间字符串，如 "2024年03月04日 星期一 14:30"
        """
        now = datetime.now()
        time_str = now.strftime("%Y年%m月%d日 %A %H:%M")
        for english_day, chinese_day in _WEEKDAY_MAP.items():
            time_str = time_str.replace(english_day, chinese_day)
        return time_str


# ─── 模块级工具函数 ───


def _truncate_content(
    content: str,
    max_chars: int = MAX_SINGLE_FILE_CHARS,
    keep_tail: bool = False,
) -> tuple[str, bool]:
    """截断过长内容.

    默认保留前 70% + 后 20%。当 keep_tail=True 时保留末尾内容
    （适用于 MEMORY.md 等按时间正序追加的文件，最新条目在末尾）。

    Args:
        content: 原始内容
        max_chars: 最大字符数
        keep_tail: 是否优先保留末尾（最新内容）

    Returns:
        (截断后的内容, 是否被截断)
    """
    if len(content) <= max_chars:
        return content, False

    if keep_tail:
        truncated = "...\n" + content[-max_chars:]
        return truncated, True

    front_size = int(max_chars * 0.7)
    back_size = int(max_chars * 0.2)
    truncated = (
        content[:front_size]
        + "\n\n[... truncated ...]\n\n"
        + content[-back_size:]
    )
    return truncated, True


def _extract_field(content: str, field_name: str) -> str:
    """从 Markdown 内容中提取 **FieldName:** value 格式的字段.

    Args:
        content: Markdown 文件内容
        field_name: 字段名（如 Name、Creature、Vibe、Emoji）

    Returns:
        字段值，未找到时返回空字符串
    """
    match = re.search(rf"\*\*{field_name}:\*\*\s*(.+)", content)
    return match.group(1).strip() if match else ""