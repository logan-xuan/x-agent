"""Plugin base class and interface for X-Agent extensibility.

This module defines the plugin contract that all X-Agent plugins must implement.
The plugin system follows the "composition over inheritance" principle.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid
from datetime import datetime


class PluginPriority(int, Enum):
    """Plugin execution priority (higher = executed first)."""
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


class PluginState(str, Enum):
    """Plugin lifecycle state."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class PluginInfo:
    """Plugin metadata and registration information."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    priority: PluginPriority = PluginPriority.NORMAL
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Plugin name is required")
        if not self.version:
            raise ValueError("Plugin version is required")


@dataclass
class PluginContext:
    """Execution context passed to plugin methods.
    
    Contains session information, user input, and shared state.
    """
    session_id: str
    user_input: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Response accumulator
    response_chunks: list[str] = field(default_factory=list)
    
    def add_chunk(self, chunk: str) -> None:
        """Add a response chunk."""
        self.response_chunks.append(chunk)
    
    def get_full_response(self) -> str:
        """Get accumulated response."""
        return "".join(self.response_chunks)


@dataclass
class PluginResult:
    """Result returned by plugin execution."""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    should_continue: bool = True  # Whether to continue plugin chain
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, output: Optional[str] = None, **metadata: Any) -> "PluginResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)
    
    @classmethod
    def error(cls, error: str, **metadata: Any) -> "PluginResult":
        """Create an error result."""
        return cls(success=False, error=error, should_continue=False, metadata=metadata)
    
    @classmethod
    def skip(cls, reason: str = "") -> "PluginResult":
        """Create a skip result (continue chain but no output)."""
        return cls(success=True, output=None, metadata={"skipped": True, "reason": reason})


class Plugin(ABC):
    """Abstract base class for all X-Agent plugins.
    
    Plugins extend X-Agent's capabilities by implementing hooks that are
    called at various points in the agent lifecycle.
    
    Example:
        class MyPlugin(Plugin):
            @property
            def info(self) -> PluginInfo:
                return PluginInfo(
                    name="my_plugin",
                    version="1.0.0",
                    description="Does something useful"
                )
            
            async def on_message(self, context: PluginContext) -> PluginResult:
                # Process message
                return PluginResult.ok("Processed")
    """
    
    _state: PluginState = PluginState.UNINITIALIZED
    _error_message: Optional[str] = None
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        pass
    
    @property
    def state(self) -> PluginState:
        """Current plugin state."""
        return self._state
    
    @property
    def is_active(self) -> bool:
        """Check if plugin is active and ready."""
        return self._state == PluginState.ACTIVE
    
    async def initialize(self) -> None:
        """Initialize plugin resources. Called once on startup.
        
        Override this method to perform async initialization.
        """
        self._state = PluginState.INITIALIZING
        try:
            await self._do_initialize()
            self._state = PluginState.ACTIVE
        except Exception as e:
            self._state = PluginState.ERROR
            self._error_message = str(e)
            raise
    
    async def _do_initialize(self) -> None:
        """Override for custom initialization logic."""
        pass
    
    async def shutdown(self) -> None:
        """Cleanup plugin resources. Called once on shutdown."""
        try:
            await self._do_shutdown()
            self._state = PluginState.STOPPED
        except Exception as e:
            self._state = PluginState.ERROR
            self._error_message = str(e)
            raise
    
    async def _do_shutdown(self) -> None:
        """Override for custom shutdown logic."""
        pass
    
    # --- Plugin Hooks (override as needed) ---
    
    async def on_message(self, context: PluginContext) -> PluginResult:
        """Called when a new message is received.
        
        Args:
            context: Execution context with user input and session info
            
        Returns:
            PluginResult indicating success/failure and any output
        """
        return PluginResult.skip()
    
    async def on_response(self, context: PluginContext, response: str) -> PluginResult:
        """Called before sending response to user.
        
        Args:
            context: Execution context
            response: The response to be sent
            
        Returns:
            PluginResult with potentially modified response
        """
        return PluginResult.ok(response)
    
    async def on_error(self, context: PluginContext, error: Exception) -> PluginResult:
        """Called when an error occurs during processing.
        
        Args:
            context: Execution context
            error: The exception that occurred
            
        Returns:
            PluginResult with error handling result
        """
        return PluginResult.error(str(error))
    
    async def on_session_start(self, context: PluginContext) -> PluginResult:
        """Called when a new session starts."""
        return PluginResult.skip()
    
    async def on_session_end(self, context: PluginContext) -> PluginResult:
        """Called when a session ends."""
        return PluginResult.skip()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.info.name}, state={self._state.value})"
