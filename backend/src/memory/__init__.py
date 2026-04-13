"""Memory system for AI Agent."""

__all__ = [
    "MemoryManager",
    "get_memory_manager",
    "init_memory_manager",
    "SpiritConfig",
    "OwnerProfile",
    "ToolDefinition",
    "MemoryEntry",
    "MemoryContentType",
    "SpiritLoader",
    "get_context_builder",
]


def __getattr__(name: str):
    if name in {
        "SpiritConfig",
        "OwnerProfile",
        "ToolDefinition",
        "MemoryEntry",
        "MemoryContentType",
    }:
        from .models import (
            MemoryContentType,
            MemoryEntry,
            OwnerProfile,
            SpiritConfig,
            ToolDefinition,
        )

        return {
            "SpiritConfig": SpiritConfig,
            "OwnerProfile": OwnerProfile,
            "ToolDefinition": ToolDefinition,
            "MemoryEntry": MemoryEntry,
            "MemoryContentType": MemoryContentType,
        }[name]
    if name == "SpiritLoader":
        from .spirit_loader import SpiritLoader

        return SpiritLoader
    if name in {"MemoryManager", "get_memory_manager", "init_memory_manager"}:
        from .manager import MemoryManager, get_memory_manager, init_memory_manager

        return {
            "MemoryManager": MemoryManager,
            "get_memory_manager": get_memory_manager,
            "init_memory_manager": init_memory_manager,
        }[name]
    if name == "get_context_builder":
        from .context_builder import ContextBuilder

        return lambda *args, **kwargs: ContextBuilder(*args, **kwargs)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
