"""Plugin manager for X-Agent.

This module provides the plugin management system that:
- Discovers and loads plugins from backend/src/plugins/
- Manages plugin lifecycle (init, shutdown, reload)
- Executes plugin hooks at various points in agent workflow
- Provides configuration and permission management
"""

import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
import asyncio

try:
    from .base import Plugin, PluginInfo, PluginContext, PluginResult, PluginState
    from ..utils.logger import get_logger
except ImportError:
    # Fallback for direct imports
    from plugins.base import Plugin, PluginInfo, PluginContext, PluginResult, PluginState
    from utils.logger import get_logger

logger = get_logger(__name__)


class PluginManager:
    """Plugin manager for discovering, loading, and executing plugins.
    
    The plugin manager follows a lifecycle:
    1. Discovery: Find all plugin modules in the plugins directory
    2. Loading: Import and instantiate plugin classes
    3. Initialization: Call initialize() on each plugin
    4. Execution: Execute plugin hooks during agent workflow
    5. Shutdown: Cleanup resources when stopping
    
    Example:
        pm = PluginManager()
        await pm.initialize_all()
        
        # Execute plugin hook
        context = PluginContext(session_id="123", user_input="hello")
        result = await pm.execute_hook("on_message", context)
        
        await pm.shutdown_all()
    """
    
    def __init__(
        self,
        plugins_dir: str = "backend/src/plugins",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize plugin manager.
        
        Args:
            plugins_dir: Directory containing plugin modules
            config: Plugin configuration (enable/disable, permissions, etc.)
        """
        self.plugins_dir = Path(plugins_dir)
        self.config = config or {}
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_infos: Dict[str, PluginInfo] = {}
        self._initialized = False
        
        logger.info(
            f"PluginManager initialized with plugins_dir={self.plugins_dir}",
            extra={"config": self.config}
        )
    
    async def initialize_all(self) -> None:
        """Discover and initialize all plugins."""
        if self._initialized:
            logger.warning("Plugins already initialized")
            return
        
        logger.info("Starting plugin discovery and initialization")
        
        # Discover plugins
        plugin_classes = await self._discover_plugins()
        
        # Load and initialize each plugin
        for plugin_cls in plugin_classes:
            try:
                await self._load_plugin(plugin_cls)
            except Exception as e:
                logger.error(
                    f"Failed to load plugin {plugin_cls.__name__}: {e}",
                    exc_info=True
                )
        
        self._initialized = True
        logger.info(
            f"Plugin initialization complete. Loaded {len(self.plugins)} plugins",
            extra={"plugin_names": list(self.plugins.keys())}
        )
    
    async def _discover_plugins(self) -> List[Type[Plugin]]:
        """Discover all plugin classes in the plugins directory.
        
        Returns:
            List of plugin classes to load
        """
        plugin_classes = []
        
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            return plugin_classes
        
        # Scan for plugin modules
        for item in self.plugins_dir.iterdir():
            if item.is_file() and item.suffix == ".py" and not item.name.startswith("_"):
                # Load module and find Plugin subclasses
                try:
                    module = await self._load_module(item)
                    classes = await self._find_plugin_classes(module)
                    plugin_classes.extend(classes)
                    logger.info(f"Discovered plugin module: {item.stem}")
                except Exception as e:
                    logger.error(f"Error scanning {item}: {e}")
            
            elif item.is_dir() and not item.name.startswith("_"):
                # Check for __init__.py in directory
                init_file = item / "__init__.py"
                if init_file.exists():
                    try:
                        module = await self._load_module(init_file)
                        classes = await self._find_plugin_classes(module)
                        plugin_classes.extend(classes)
                        logger.info(f"Discovered plugin package: {item.name}")
                    except Exception as e:
                        logger.error(f"Error scanning package {item}: {e}")
        
        return plugin_classes
    
    async def _load_module(self, file_path: Path) -> Any:
        """Load a Python module from file path.
        
        Args:
            file_path: Path to .py file
            
        Returns:
            Imported module
        """
        module_name = f"plugins.{file_path.stem}"
        
        # Use synchronous import (async doesn't compatible with importlib)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec from {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        return module
    
    async def _find_plugin_classes(self, module: Any) -> List[Type[Plugin]]:
        """Find all Plugin subclasses in a module.
        
        Args:
            module: Python module to scan
            
        Returns:
            List of Plugin subclass types
        """
        plugin_classes = []
        
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's a Plugin subclass but not Plugin itself
            if issubclass(obj, Plugin) and obj is not Plugin:
                # Check if it has required info property
                try:
                    # Try to instantiate (will fail for abstract classes)
                    # We just check if it's concrete
                    if hasattr(obj, 'info') and inspect.ismethod(getattr(obj, 'info')):
                        plugin_classes.append(obj)
                except Exception:
                    pass
        
        return plugin_classes
    
    async def _load_plugin(self, plugin_cls: Type[Plugin]) -> None:
        """Load and initialize a single plugin.
        
        Args:
            plugin_cls: Plugin class to load
        """
        # Check if plugin is enabled
        info_property = getattr(plugin_cls, 'info', None)
        if info_property is None:
            raise ValueError(f"Plugin {plugin_cls.__name__} missing 'info' property")
        
        # Create instance
        plugin_instance = plugin_cls()
        
        # Get plugin info
        try:
            info = plugin_instance.info
            if not isinstance(info, PluginInfo):
                raise TypeError(f"Plugin info must be PluginInfo instance, got {type(info)}")
        except Exception as e:
            raise ValueError(f"Failed to get plugin info: {e}")
        
        # Check if disabled
        plugin_config = self.config.get("plugins", {}).get(info.name, {})
        if plugin_config.get("enabled", True) is False:
            logger.info(f"Plugin {info.name} is disabled by config")
            return
        
        # Initialize plugin
        logger.info(f"Initializing plugin: {info.name} v{info.version}")
        await plugin_instance.initialize()
        
        # Store loaded plugin
        self.plugins[info.name] = plugin_instance
        self.plugin_infos[info.name] = info
        
        logger.info(f"✅ Plugin loaded: {info.name} ({info.state.value})")
    
    async def execute_hook(
        self,
        hook_name: str,
        context: PluginContext,
        *args: Any,
        **kwargs: Any,
    ) -> List[PluginResult]:
        """Execute a plugin hook across all active plugins.
        
        Plugins are executed in priority order (highest first).
        If any plugin returns should_continue=False, execution stops.
        
        Args:
            hook_name: Name of hook to execute (e.g., "on_message")
            context: Plugin execution context
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            List of results from executed plugins
        """
        if not self._initialized:
            logger.warning("Plugins not initialized, skipping hook execution")
            return []
        
        results = []
        
        # Sort plugins by priority (highest first)
        sorted_plugins = sorted(
            self.plugins.items(),
            key=lambda x: x[1].info.priority.value,
            reverse=True
        )
        
        for plugin_name, plugin in sorted_plugins:
            if not plugin.is_active:
                continue
            
            try:
                # Get hook method
                hook_method = getattr(plugin, hook_name, None)
                if hook_method is None:
                    continue
                
                # Check if method accepts correct signature
                sig = inspect.signature(hook_method)
                params = list(sig.parameters.values())
                
                # Build arguments
                call_args = [context] + list(args)
                
                # Execute hook
                if asyncio.iscoroutinefunction(hook_method):
                    result = await hook_method(*call_args, **kwargs)
                else:
                    result = hook_method(*call_args, **kwargs)
                
                if not isinstance(result, PluginResult):
                    logger.warning(
                        f"Plugin {plugin_name} hook {hook_name} returned invalid type: {type(result)}"
                    )
                    continue
                
                results.append(result)
                
                # Check if should stop chain
                if not result.should_continue:
                    logger.debug(
                        f"Plugin {plugin_name} stopped hook chain at {hook_name}"
                    )
                    break
                    
            except Exception as e:
                logger.error(
                    f"Plugin {plugin_name} hook {hook_name} failed: {e}",
                    exc_info=True
                )
                results.append(PluginResult.error(str(e)))
        
        return results
    
    async def shutdown_all(self) -> None:
        """Shutdown all plugins and cleanup resources."""
        logger.info("Shutting down all plugins")
        
        for plugin_name, plugin in list(self.plugins.items()):
            try:
                await plugin.shutdown()
                logger.info(f"Plugin shutdown: {plugin_name}")
            except Exception as e:
                logger.error(
                    f"Error shutting down {plugin_name}: {e}",
                    exc_info=True
                )
        
        self.plugins.clear()
        self.plugin_infos.clear()
        self._initialized = False
        
        logger.info("All plugins shut down")
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin instance or None if not found
        """
        return self.plugins.get(name)
    
    def get_plugin_info(self, name: str) -> Optional[PluginInfo]:
        """Get plugin metadata.
        
        Args:
            name: Plugin name
            
        Returns:
            PluginInfo or None
        """
        return self.plugin_infos.get(name)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins with their status.
        
        Returns:
            List of plugin information dictionaries
        """
        return [
            {
                "name": info.name,
                "version": info.version,
                "description": info.description,
                "author": info.author,
                "priority": info.priority.name,
                "tags": info.tags,
                "state": plugin.state.value,
                "is_active": plugin.is_active,
            }
            for name, info in self.plugin_infos.items()
            if (plugin := self.plugins.get(name))
        ]
    
    async def reload_plugin(self, name: str) -> bool:
        """Reload a plugin (unload + load).
        
        Args:
            name: Plugin name to reload
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Reloading plugin: {name}")
        
        # Unload
        if name in self.plugins:
            try:
                await self.plugins[name].shutdown()
                del self.plugins[name]
                del self.plugin_infos[name]
                logger.info(f"Unloaded plugin: {name}")
            except Exception as e:
                logger.error(f"Error unloading {name}: {e}")
                return False
        
        # Find plugin class again (simplified - in production would cache class refs)
        plugin_classes = await self._discover_plugins()
        target_class = next(
            (cls for cls in plugin_classes if cls().info.name == name),
            None
        )
        
        if target_class is None:
            logger.error(f"Cannot find plugin class for: {name}")
            return False
        
        # Load
        try:
            await self._load_plugin(target_class)
            logger.info(f"✅ Reloaded plugin: {name}")
            return True
        except Exception as e:
            logger.error(f"Error loading {name}: {e}")
            return False


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager(config: Optional[Dict[str, Any]] = None) -> PluginManager:
    """Get or create the global plugin manager.
    
    Args:
        config: Optional configuration override
        
    Returns:
        PluginManager instance
    """
    global _plugin_manager
    
    if _plugin_manager is None:
        _plugin_manager = PluginManager(config=config)
    
    return _plugin_manager


async def initialize_plugins(config: Optional[Dict[str, Any]] = None) -> PluginManager:
    """Initialize the global plugin manager.
    
    Args:
        config: Plugin configuration
        
    Returns:
        Initialized PluginManager
    """
    pm = get_plugin_manager(config)
    await pm.initialize_all()
    return pm


async def shutdown_plugins() -> None:
    """Shutdown all plugins."""
    if _plugin_manager:
        await _plugin_manager.shutdown_all()
