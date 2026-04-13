"""Multi-Agent Context Loader.

This module provides context loading for multiple agents based on configuration.
Each agent can have its own workspace directory with separate context files.

Supports loading:
- AGENTS.md (agent guidance)
- BOOTSTRAP.md (bootstrap instructions)
- IDENTITY.md (AI identity)
- MEMORY.md (long-term memory)
- OWNER.md (user profile)
- SPIRIT.md (AI personality)
- TOOLS.md (tool definitions)
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config.models import AgentConfig, MultiAgentConfig
from ..conversation.context_loader import ContextLoader
from ..utils.logger import get_logger

logger = get_logger(__name__)

# ─── 全局单例 ───

_multi_agent_context_loader: Optional["MultiAgentContextLoader"] = None


def set_multi_agent_context_loader(loader: "MultiAgentContextLoader") -> None:
    """注册全局 MultiAgentContextLoader 单例（由 main.py 启动时调用）。"""
    global _multi_agent_context_loader
    _multi_agent_context_loader = loader


def get_multi_agent_context_loader() -> Optional["MultiAgentContextLoader"]:
    """获取全局 MultiAgentContextLoader 单例。"""
    return _multi_agent_context_loader


class AgentContextInfo:
    """Context information for a single agent."""

    def __init__(self, agent_id: str, workspace_path: str):
        """Initialize agent context info.

        Args:
            agent_id: Agent identifier
            workspace_path: Path to agent's workspace directory
        """
        self.agent_id = agent_id
        self.workspace_path = Path(workspace_path).expanduser()
        self.context_loader: ContextLoader | None = None
        self.loaded_at: datetime | None = None
        self.context_files: dict[str, bool] = {}  # filename -> exists

    def load_context_files(self) -> dict[str, bool]:
        """Load and check existence of context files.

        Returns:
            Dictionary mapping filename to existence status
        """
        context_files = [
            "AGENTS.md",
            "BOOTSTRAP.md",
            "IDENTITY.md",
            "MEMORY.md",
            "OWNER.md",
            "SPIRIT.md",
            "TOOLS.md",
        ]

        self.context_files = {}
        for filename in context_files:
            file_path = self.workspace_path / filename
            exists = file_path.exists()
            self.context_files[filename] = exists

            if exists:
                logger.info(
                    "Context file loaded",
                    extra={
                        "agent_id": self.agent_id,
                        "filename": filename,
                        "path": str(file_path),
                    },
                )
            else:
                logger.debug(
                    "Context file not found",
                    extra={
                        "agent_id": self.agent_id,
                        "filename": filename,
                        "path": str(file_path),
                    },
                )

        self.loaded_at = datetime.now()
        return self.context_files

    def get_context_loader(self) -> ContextLoader:
        """Get or create context loader for this agent.

        Returns:
            ContextLoader instance
        """
        if self.context_loader is None:
            self.context_loader = ContextLoader(str(self.workspace_path))
            logger.info(
                "ContextLoader created for agent",
                extra={
                    "agent_id": self.agent_id,
                    "workspace_path": str(self.workspace_path),
                },
            )
        return self.context_loader


class MultiAgentContextLoader:
    """Context loader for multiple agents.

    Manages context loading for all agents defined in configuration.
    Each agent can have its own workspace directory with separate context files.
    """

    def __init__(self, multi_agent_config: MultiAgentConfig):
        """Initialize multi-agent context loader.

        Args:
            multi_agent_config: Multi-agent configuration from x-agent.yaml
        """
        self.multi_agent_config = multi_agent_config
        self.agent_contexts: dict[str, AgentContextInfo] = {}

        logger.info(
            "MultiAgentContextLoader initialized",
            extra={"agent_count": len(multi_agent_config.agents)},
        )

    def initialize_all_agents(self) -> dict[str, dict[str, bool]]:
        """Initialize context for all agents.

        Returns:
            Dictionary mapping agent_id to their context files status
        """
        results = {}

        for agent_config in self.multi_agent_config.agents:
            try:
                workspace_path = self._resolve_workspace_path(agent_config)
                agent_context = AgentContextInfo(agent_config.id, str(workspace_path))
                self.agent_contexts[agent_config.id] = agent_context

                # Load context files
                context_files = agent_context.load_context_files()
                results[agent_config.id] = context_files

                logger.info(
                    "Agent context initialized",
                    extra={
                        "agent_id": agent_config.id,
                        "agent_name": agent_config.name,
                        "workspace_path": str(workspace_path),
                        "files_loaded": sum(1 for v in context_files.values() if v),
                    },
                )

            except Exception as e:
                logger.error(
                    "Failed to initialize agent context",
                    extra={
                        "agent_id": agent_config.id,
                        "error": str(e),
                    },
                )
                results[agent_config.id] = {}

        return results

    def _resolve_workspace_path(self, agent_config: AgentConfig) -> Path:
        """Resolve agent's workspace path.

        Args:
            agent_config: Agent configuration

        Returns:
            Resolved workspace path
        """
        workspace = agent_config.workspace or "workspace"

        # Expand user home directory (~)
        workspace_path = Path(workspace).expanduser()

        # If relative path, make it relative to project root
        if not workspace_path.is_absolute():
            # Assume relative to backend directory
            backend_dir = Path(__file__).parent.parent
            workspace_path = (backend_dir / workspace_path).resolve()

        return workspace_path

    def get_agent_context(self, agent_id: str) -> AgentContextInfo | None:
        """Get context info for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentContextInfo or None if not found
        """
        return self.agent_contexts.get(agent_id)

    def get_context_loader(self, agent_id: str) -> ContextLoader | None:
        """Get context loader for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            ContextLoader or None if not found
        """
        agent_context = self.get_agent_context(agent_id)
        if agent_context:
            return agent_context.get_context_loader()
        return None

    def reload_agent_context(self, agent_id: str) -> dict[str, bool] | None:
        """Reload context files for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Context files status or None if agent not found
        """
        agent_context = self.get_agent_context(agent_id)
        if agent_context:
            return agent_context.load_context_files()
        return None

    def get_all_loaded_files(self) -> dict[str, list[str]]:
        """Get all loaded context files for all agents.

        Returns:
            Dictionary mapping agent_id to list of loaded file paths
        """
        result = {}

        for agent_id, agent_context in self.agent_contexts.items():
            files = []
            for filename, exists in agent_context.context_files.items():
                if exists:
                    file_path = agent_context.workspace_path / filename
                    files.append(str(file_path))
            result[agent_id] = files

        return result
