"""Execution mode definitions for Cron scheduler.

This module defines different execution modes for agent tasks,
allowing fine-grained control over the execution granularity.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any


class ExecutionMode(str, Enum):
    """Execution mode for agent tasks.
    
    Defines the granularity of agent execution:
    - LIGHT: Lightweight mode with minimal overhead
    - STANDARD: Full agent loop with all capabilities
    - FUNCTION: Direct function execution without LLM
    """
    LIGHT = "light"         # 轻量模式：直接调用 LLM，无工具/记忆
    STANDARD = "standard"   # 标准模式：完整 Agent 循环（当前行为）
    FUNCTION = "function"   # 函数模式：直接调用指定工具，跳过 LLM


@dataclass
class ExecutionModeConfig:
    """Configuration for execution modes.
    
    Attributes:
        mode: The execution mode
        llm_enabled: Whether to use LLM
        tools_enabled: Whether tools are available
        memory_enabled: Whether memory is available
        max_iterations: Maximum iterations for agent loop (STANDARD mode)
        timeout_seconds: Execution timeout
    """
    mode: ExecutionMode = ExecutionMode.STANDARD
    llm_enabled: bool = True
    tools_enabled: bool = True
    memory_enabled: bool = True
    max_iterations: int = 10
    timeout_seconds: float = 300.0
    
    def __post_init__(self):
        """Auto-configure based on mode."""
        if self.mode == ExecutionMode.LIGHT:
            self.llm_enabled = True
            self.tools_enabled = False
            self.memory_enabled = False
            self.max_iterations = 1
        elif self.mode == ExecutionMode.FUNCTION:
            self.llm_enabled = False
            self.tools_enabled = True  # Function mode uses tools directly
            self.memory_enabled = False
            self.max_iterations = 1
        # STANDARD mode uses defaults (all enabled)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "llm_enabled": self.llm_enabled,
            "tools_enabled": self.tools_enabled,
            "memory_enabled": self.memory_enabled,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
        }
    
    @classmethod
    def from_mode(cls, mode: ExecutionMode | str) -> "ExecutionModeConfig":
        """Create config from mode enum or string.
        
        Args:
            mode: Execution mode (enum or string value)
            
        Returns:
            ExecutionModeConfig instance
        """
        if isinstance(mode, str):
            mode = ExecutionMode(mode)
        return cls(mode=mode)


# Default configurations for each mode
DEFAULT_LIGHT_CONFIG = ExecutionModeConfig(mode=ExecutionMode.LIGHT)
DEFAULT_STANDARD_CONFIG = ExecutionModeConfig(mode=ExecutionMode.STANDARD)
DEFAULT_FUNCTION_CONFIG = ExecutionModeConfig(mode=ExecutionMode.FUNCTION)
