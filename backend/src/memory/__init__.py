"""Memory system for AI Agent.

This module provides self-awareness and memory evolution capabilities:
- MemoryManager: Unified entry point for all memory operations
- SpiritLoader: Load and parse SPIRIT.md (AI personality) and OWNER.md (user profile)
- ContextBuilder: Context data loading (identity, tools, memory)
- VectorStore: sqlite-vss based vector storage
- HybridSearch: Semantic + keyword search (0.7 vector + 0.3 text)
- FileWatcher: Hot-reload and bidirectional sync
- MdSync: Markdown ↔ Vector storage synchronization
- Embedder: Text embedding generation
"""

from .models import (
    SpiritConfig,
    OwnerProfile,
    ToolDefinition,
    MemoryEntry,
    MemoryContentType,
)
from .spirit_loader import SpiritLoader
from .manager import MemoryManager, get_memory_manager, init_memory_manager

# ContextBuilder imported lazily to avoid circular imports
# from .context_builder import ContextBuilder

def get_context_builder(*args, **kwargs):
    """Lazy import to avoid circular imports."""
    from .context_builder import ContextBuilder
    return ContextBuilder(*args, **kwargs)

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
