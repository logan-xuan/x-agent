"""Configuration manager with hot-reload support."""

import threading
from pathlib import Path
from typing import Callable

from .loader import ConfigLoadError, load_config
from .models import Config


class ConfigManager:
    """Singleton configuration manager with hot-reload support.
    
    This class provides thread-safe access to configuration with:
    - Lazy loading on first access
    - Hot-reload capability via file watcher
    - Callback registration for config changes
    """
    
    _instance: "ConfigManager | None" = None
    _lock = threading.Lock()
    
    def __new__(cls, config_path: Path | None = None) -> "ConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_path: Path | None = None) -> None:
        if self._initialized:
            return
            
        self._config_path = config_path or Path("x-agent.yaml")
        self._config: Config | None = None
        self._callbacks: list[Callable[[Config], None]] = []
        self._watcher = None
        self._lock = threading.RLock()
        self._initialized = True
    
    @property
    def config(self) -> Config:
        """Get current configuration, loading if necessary."""
        with self._lock:
            if self._config is None:
                self._load()
            return self._config
    
    @property
    def config_path(self) -> Path:
        """Get configuration file path."""
        return self._config_path
    
    def _load(self) -> None:
        """Load configuration from file."""
        try:
            self._config = load_config(self._config_path)
        except ConfigLoadError as e:
            raise RuntimeError(f"Failed to load configuration: {e}")
    
    def reload(self) -> None:
        """Reload configuration from file."""
        with self._lock:
            old_config = self._config
            self._load()
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(self._config)
                except Exception as e:
                    # Log but don't fail if callback errors
                    print(f"Config change callback failed: {e}")
    
    def on_change(self, callback: Callable[[Config], None]) -> None:
        """Register a callback to be called when configuration changes.
        
        Args:
            callback: Function to call with new Config instance
        """
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[Config], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start_watcher(self) -> None:
        """Start file watcher for hot-reload (optional).
        
        Requires watchdog to be installed.
        """
        try:
            from .watcher import ConfigWatcher
            
            if self._watcher is None:
                self._watcher = ConfigWatcher(self._config_path, self.reload)
                self._watcher.start()
        except ImportError:
            print("watchdog not installed, hot-reload disabled")
    
    def stop_watcher(self) -> None:
        """Stop file watcher."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
    
    def get(self) -> Config:
        """Get configuration (convenience method)."""
        return self.config


def get_config() -> Config:
    """Get global configuration instance.
    
    This is a convenience function that returns the ConfigManager singleton's config.
    """
    return ConfigManager().config
