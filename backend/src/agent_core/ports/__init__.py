"""Agent Core Port 接口定义.

本模块定义了 agent_core 的所有 Port 接口，使用 Protocol 实现结构化子类型。

Port 接口:
- LLMPort: LLM 调用接口
- ToolPort: 工具执行接口
- MemoryPort: 记忆存储接口
- LoggerPort: 日志接口
"""

from .llm_port import LLMPort
from .tool_port import ToolPort
from .memory_port import MemoryPort
from .logger_port import LoggerPort

__all__ = [
    "LLMPort",
    "ToolPort",
    "MemoryPort",
    "LoggerPort",
]
