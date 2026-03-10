"""CLI 本地配置管理。

管理 CLI 的连接配置、默认参数等。
支持从环境变量和配置文件加载。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CLIConfig:
    """CLI 配置。

    Attributes:
        server_url: Backend 服务地址（Remote 模式）。
        mode: 运行模式，"remote" 或 "embedded"。
        default_session_id: 默认会话 ID（None 表示每次新建）。
        timeout: HTTP 请求超时时间（秒）。
        show_thinking: 是否显示思考过程。
        show_tool_calls: 是否显示工具调用详情。
    """
    server_url: str = "http://localhost:5177"
    mode: Literal["remote", "embedded"] = "remote"
    default_session_id: str | None = None
    timeout: float = 300.0
    show_thinking: bool = False
    show_tool_calls: bool = True
    admin_token: str = "x-agent-admin-token-88888"

    @classmethod
    def from_env(cls) -> CLIConfig:
        """从环境变量加载配置。

        环境变量前缀为 XAGENT_，例如：
        - XAGENT_SERVER_URL=http://localhost:5177
        - XAGENT_MODE=remote
        - XAGENT_TIMEOUT=300
        - XAGENT_SHOW_THINKING=true

        Returns:
            CLIConfig 实例。
        """
        mode_value: Literal["remote", "embedded"] = (
            "embedded" if os.getenv("XAGENT_MODE", "remote") == "embedded" else "remote"
        )
        return cls(
            server_url=os.getenv("XAGENT_SERVER_URL", "http://localhost:5177"),
            mode=mode_value,
            default_session_id=os.getenv("XAGENT_SESSION_ID"),
            timeout=float(os.getenv("XAGENT_TIMEOUT", "300")),
            show_thinking=os.getenv("XAGENT_SHOW_THINKING", "").lower() in ("true", "1", "yes"),
            show_tool_calls=os.getenv("XAGENT_SHOW_TOOL_CALLS", "true").lower() in ("true", "1", "yes"),
            admin_token=os.getenv("XAGENT_ADMIN_TOKEN", "x-agent-admin-token-88888"),
        )
