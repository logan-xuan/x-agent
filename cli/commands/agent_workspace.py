"""Agent 工作空间初始化模块。

负责根据 backend/docs/bootstrap 中的模板文件，
在指定路径初始化新 Agent 的工作空间目录结构和配置文件。

生成结构：
    <workspace>/
    ├── agent.yaml          # Agent 配置文件
    ├── AGENTS.md           # 工作空间使用指南（来自模板）
    ├── BOOTSTRAP.md        # 首次启动引导（来自模板，含人设占位符替换）
    ├── SPIRIT.md           # 人格设定（来自模板）
    ├── IDENTITY.md         # 身份信息（来自模板）
    ├── OWNER.md            # 用户画像（来自模板）
    ├── MEMORY.md           # 长期记忆（来自模板）
    ├── TOOLS.md            # 工具定义（来自模板）
    ├── HEARTBEAT.md        # 心跳任务（来自模板）
    └── memory/             # 每日记忆目录
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

# bootstrap 模板目录相对于项目根目录的路径
_BOOTSTRAP_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "backend" / "docs" / "bootstrap"

# 需要从模板复制的文件列表（按顺序）
_TEMPLATE_FILES = [
    "AGENTS.md",
    "BOOTSTRAP.md",
    "SPIRIT.md",
    "IDENTITY.md",
    "OWNER.md",
    "MEMORY.md",
    "TOOLS.md",
    "HEARTBEAT.md",
]


def create_agent_workspace(
    *,
    agent_id: str,
    agent_name: str,
    persona: str,
    workspace_path: str,
) -> list[str]:
    """初始化 Agent 工作空间目录和配置文件。

    Args:
        agent_id: Agent 唯一标识符。
        agent_name: Agent 名称。
        persona: Agent 人设描述。
        workspace_path: 工作空间目标路径（相对或绝对路径）。

    Returns:
        已创建的文件路径列表（相对于工作空间根目录）。

    Raises:
        FileExistsError: 工作空间目录已存在且非空时抛出。
    """
    workspace = Path(workspace_path)

    if workspace.exists() and any(workspace.iterdir()):
        raise FileExistsError(
            f"工作空间目录 '{workspace}' 已存在且不为空，请指定一个新路径。"
        )

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)

    created_files: list[str] = []

    # ── 生成 agent.yaml 配置文件 ─────────────────────────────────────────
    yaml_path = workspace / "agent.yaml"
    yaml_path.write_text(
        _render_agent_yaml(
            agent_id=agent_id,
            agent_name=agent_name,
            persona=persona,
            workspace_path=str(workspace.resolve()),
        ),
        encoding="utf-8",
    )
    created_files.append("agent.yaml")

    # ── 从模板复制并渲染工作空间文件 ─────────────────────────────────────
    template_vars = {
        "{{AGENT_ID}}": agent_id,
        "{{AGENT_NAME}}": agent_name,
        "{{AGENT_PERSONA}}": persona,
        "{{WORKSPACE_PATH}}": str(workspace.resolve()),
        "{{CREATED_AT}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    for template_filename in _TEMPLATE_FILES:
        template_file = _BOOTSTRAP_TEMPLATE_DIR / template_filename
        target_file = workspace / template_filename

        if template_file.exists():
            content = template_file.read_text(encoding="utf-8")
            rendered_content = _render_template(content, template_vars)
            target_file.write_text(rendered_content, encoding="utf-8")
        else:
            # 模板文件不存在时生成空占位文件
            target_file.write_text(
                f"# {template_filename}\n\n（待填写）\n",
                encoding="utf-8",
            )

        created_files.append(template_filename)

    # ── 生成今日记忆文件 ─────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    daily_memory_path = workspace / "memory" / f"{today}.md"
    daily_memory_path.write_text(
        f"# {today} - {agent_name} 的第一天\n\n"
        f"Agent 工作空间初始化完成。\n\n"
        f"- Agent ID: {agent_id}\n"
        f"- 名称: {agent_name}\n"
        f"- 人设: {persona}\n",
        encoding="utf-8",
    )
    created_files.append(f"memory/{today}.md")

    return created_files


def _render_template(content: str, variables: dict[str, str]) -> str:
    """将模板内容中的占位符替换为实际值。

    Args:
        content: 模板文件原始内容。
        variables: 占位符到实际值的映射字典。

    Returns:
        替换后的内容字符串。
    """
    for placeholder, value in variables.items():
        content = content.replace(placeholder, value)
    return content


def _render_agent_yaml(
    *,
    agent_id: str,
    agent_name: str,
    persona: str,
    workspace_path: str,
) -> str:
    """生成 agent.yaml 配置文件内容。

    Args:
        agent_id: Agent 唯一标识符。
        agent_name: Agent 名称。
        persona: Agent 人设描述。
        workspace_path: 工作空间绝对路径。

    Returns:
        YAML 格式的配置文件内容字符串。
    """
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 对多行 persona 进行 YAML 块标量处理
    persona_yaml = _to_yaml_literal_block(persona, indent=2)

    return f"""\
# Agent 配置文件
# 由 x-agent agent create 命令自动生成于 {created_at}

agent_id: {agent_id}
agent_name: "{agent_name}"

# 人设描述：定义 Agent 的性格、角色和行为准则
persona: |
{persona_yaml}

# 工作空间路径：存放记忆、身份、工具等文件的目录
workspace: "{workspace_path}"

# 创建时间
created_at: "{created_at}"
"""


def _to_yaml_literal_block(text: str, indent: int = 2) -> str:
    """将多行文本转换为 YAML 字面块标量格式（每行前加缩进）。

    Args:
        text: 原始文本内容。
        indent: 缩进空格数。

    Returns:
        带缩进的多行字符串。
    """
    prefix = " " * indent
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())
