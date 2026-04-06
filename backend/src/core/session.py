"""Compatibility shim for legacy src.core.session imports."""

try:
    from ..conversation.session import SessionManager
except ImportError:  # 顶层 core.* 导入兼容
    from conversation.session import SessionManager  # type: ignore

__all__ = ["SessionManager"]
