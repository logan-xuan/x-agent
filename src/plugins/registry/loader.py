"""
Plugin loader for the x-agent2 AI assistant system.

This module handles the dynamic loading, registration, and management of plugins
that extend the system's functionality.
"""

import os
import sys
import importlib.util
import inspect
from typing import Optional, Dict, List, Any, Type, Callable
from pathlib import Path
import json
import hashlib
from datetime import datetime
import logging
from enum import Enum

from src.db.models.plugin import Plugin
from src.agent_core.config.config_service import get_config


class PluginLoadStatus(Enum):
    """Status of plugin loading operations."""
    SUCCESS = "success"
    FAILED_VALIDATION = "failed_validation"
    FAILED_IMPORT = "failed_import"
    FAILED_DEPENDENCIES = "failed_dependencies"
    INCOMPATIBLE_VERSION = "incompatible_version"


class PluginManifest:
    """Represents a plugin's manifest containing metadata and configuration."""

    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "")
        self.version = kwargs.get("version", "1.0.0")
        self.description = kwargs.get("description", "")
        self.author = kwargs.get("author", "")
        self.license = kwargs.get("license", "MIT")
        self.repository = kwargs.get("repository", "")
        self.main_module = kwargs.get("main_module", "")
        self.entry_point = kwargs.get("entry_point", "")
        self.dependencies = kwargs.get("dependencies", [])
        self.min_xagent_version = kwargs.get("min_xagent_version", "1.0.0")
        self.permissions = kwargs.get("permissions", [])
        self.enabled = kwargs.get("enabled", True)
        self.config_schema = kwargs.get("config_schema", {})
        self.tags = kwargs.get("tags", [])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginManifest':
        """Create a PluginManifest from a dictionary."""
        return cls(**data)

    @classmethod
    def from_file(cls, manifest_path: str) -> 'PluginManifest':
        """Load a PluginManifest from a JSON file."""
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the PluginManifest to a dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "repository": self.repository,
            "main_module": self.main_module,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "min_xagent_version": self.min_xagent_version,
            "permissions": self.permissions,
            "enabled": self.enabled,
            "config_schema": self.config_schema,
            "tags": self.tags
        }


class PluginLoader:
    """Manages the loading and registration of plugins."""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Plugin storage
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_manifests: Dict[str, PluginManifest] = {}
        self.plugin_instances: Dict[str, Any] = {}

        # Plugin search paths
        self.plugin_dirs = [
            Path("plugins"),
            Path("workspace/custom-skills"),
            Path("workspace/user-plugins")
        ]

    def discover_plugins(self, search_dirs: Optional[List[Path]] = None) -> List[Path]:
        """
        Discover plugins in the specified directories.

        Args:
            search_dirs: Optional list of directories to search in

        Returns:
            List of paths to plugin directories
        """
        search_directories = search_dirs or self.plugin_dirs
        plugin_paths = []

        for search_dir in search_directories:
            if not search_dir.exists():
                continue

            # Look for plugin.json or plugin.yaml manifests
            for manifest_file in search_dir.glob("**/plugin.json"):
                plugin_dir = manifest_file.parent
                plugin_paths.append(plugin_dir)

            # Also look for Python package structures
            for plugin_dir in search_dir.iterdir():
                if plugin_dir.is_dir():
                    # Check for __init__.py and plugin.json
                    init_file = plugin_dir / "__init__.py"
                    manifest_file = plugin_dir / "plugin.json"

                    if init_file.exists() and manifest_file.exists():
                        plugin_paths.append(plugin_dir)

        return plugin_paths

    def load_plugin_manifest(self, plugin_path: Path) -> Optional[PluginManifest]:
        """
        Load the manifest for a plugin.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            PluginManifest if successful, None otherwise
        """
        manifest_path = plugin_path / "plugin.json"

        if not manifest_path.exists():
            self.logger.error(f"Plugin manifest not found at {manifest_path}")
            return None

        try:
            manifest = PluginManifest.from_file(str(manifest_path))
            self.plugin_manifests[manifest.name] = manifest
            return manifest
        except Exception as e:
            self.logger.error(f"Failed to load plugin manifest from {manifest_path}: {e}")
            return None

    def validate_plugin(self, manifest: PluginManifest, plugin_path: Path) -> Dict[str, Any]:
        """
        Validate a plugin based on its manifest and path.

        Args:
            manifest: Plugin manifest to validate
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []

        # Validate required fields
        if not manifest.name:
            errors.append("Plugin name is required")
        if not manifest.version:
            errors.append("Plugin version is required")
        if not manifest.main_module:
            errors.append("Plugin main module is required")
        if not manifest.entry_point:
            errors.append("Plugin entry point is required")

        # Validate version format (simple check)
        version_parts = manifest.version.split('.')
        if len(version_parts) < 2 or not all(p.isdigit() for p in version_parts):
            warnings.append(f"Version format for {manifest.name} might be invalid: {manifest.version}")

        # Check if main module file exists
        main_module_path = plugin_path / manifest.main_module
        if not main_module_path.exists():
            errors.append(f"Main module file does not exist: {main_module_path}")

        # Check dependencies
        for dep in manifest.dependencies:
            if not self.is_plugin_installed(dep):
                warnings.append(f"Dependency '{dep}' is not installed: {manifest.name}")

        # Check compatibility with x-agent2 version
        system_version = self.config.version
        if manifest.min_xagent_version > system_version:
            errors.append(f"Plugin requires x-agent2 version {manifest.min_xagent_version}, "
                         f"but system is running {system_version}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def is_plugin_installed(self, plugin_name: str) -> bool:
        """Check if a plugin is already installed."""
        try:
            plugin_db = Plugin.get_by_name(plugin_name)
            return plugin_db is not None
        except Exception:
            # If database access fails, check if it's loaded in memory
            return plugin_name in self.loaded_plugins

    def load_plugin_module(self, manifest: PluginManifest, plugin_path: Path) -> Optional[Any]:
        """
        Dynamically load a plugin module.

        Args:
            manifest: Plugin manifest
            plugin_path: Path to the plugin directory

        Returns:
            Loaded module if successful, None otherwise
        """
        module_path = plugin_path / manifest.main_module

        if not module_path.exists():
            self.logger.error(f"Plugin module file does not exist: {module_path}")
            return None

        try:
            # Generate a unique module name to avoid conflicts
            module_name = f"plugin_{manifest.name}_{hashlib.md5(plugin_path.as_posix().encode()).hexdigest()}"

            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                self.logger.error(f"Could not create module spec for {module_path}")
                return None

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules to make it importable
            sys.modules[module_name] = module

            # Execute the module to load its contents
            spec.loader.exec_module(module)

            return module
        except Exception as e:
            self.logger.error(f"Failed to load plugin module {module_path}: {e}")
            return None

    def instantiate_plugin(self, manifest: PluginManifest, module: Any) -> Optional[Any]:
        """
        Instantiate a plugin from its module.

        Args:
            manifest: Plugin manifest
            module: Loaded plugin module

        Returns:
            Plugin instance if successful, None otherwise
        """
        try:
            # Get the entry point class/function from the module
            if hasattr(module, manifest.entry_point):
                entry_point = getattr(module, manifest.entry_point)

                # Check if it's a class that can be instantiated
                if inspect.isclass(entry_point):
                    # Create an instance of the plugin class
                    plugin_instance = entry_point()
                    return plugin_instance
                elif callable(entry_point):
                    # Call the entry point function
                    plugin_instance = entry_point()
                    return plugin_instance
                else:
                    self.logger.error(f"Entry point {manifest.entry_point} is neither a class nor a callable")
                    return None
            else:
                self.logger.error(f"Entry point {manifest.entry_point} not found in module")
                return None
        except Exception as e:
            self.logger.error(f"Failed to instantiate plugin {manifest.name}: {e}")
            return None

    def register_plugin_with_system(self, plugin_name: str, plugin_instance: Any, manifest: PluginManifest) -> bool:
        """
        Register a loaded plugin with the system.

        Args:
            plugin_name: Name of the plugin
            plugin_instance: Instantiated plugin object
            manifest: Plugin manifest

        Returns:
            True if registration was successful, False otherwise
        """
        try:
            # Register with the plugin registry in the database
            plugin_record = Plugin(
                id=None,  # Will be auto-generated
                name=plugin_name,
                version=manifest.version,
                description=manifest.description,
                author=manifest.author,
                license=manifest.license,
                repository=manifest.repository,
                enabled=manifest.enabled,
                metadata=manifest.to_dict(),
                installed_at=datetime.utcnow()
            )

            # Save the plugin record to the database
            plugin_record.save()

            # Store in memory
            self.loaded_plugins[plugin_name] = plugin_instance
            self.plugin_instances[plugin_name] = plugin_instance

            self.logger.info(f"Plugin {plugin_name} registered successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to register plugin {plugin_name} with system: {e}")
            return False

    def load_plugin(self, plugin_path: Path) -> Dict[str, Any]:
        """
        Load a plugin from the specified path.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with loading results
        """
        # Load manifest
        manifest = self.load_plugin_manifest(plugin_path)
        if not manifest:
            return {
                "status": PluginLoadStatus.FAILED_IMPORT.value,
                "message": "Failed to load plugin manifest",
                "plugin_path": str(plugin_path)
            }

        # Validate plugin
        validation_result = self.validate_plugin(manifest, plugin_path)
        if not validation_result["is_valid"]:
            return {
                "status": PluginLoadStatus.FAILED_VALIDATION.value,
                "message": f"Plugin validation failed: {'; '.join(validation_result['errors'])}",
                "plugin_path": str(plugin_path),
                "validation_errors": validation_result["errors"]
            }

        # Load plugin module
        module = self.load_plugin_module(manifest, plugin_path)
        if not module:
            return {
                "status": PluginLoadStatus.FAILED_IMPORT.value,
                "message": "Failed to load plugin module",
                "plugin_path": str(plugin_path)
            }

        # Instantiate plugin
        instance = self.instantiate_plugin(manifest, module)
        if not instance:
            return {
                "status": PluginLoadStatus.FAILED_IMPORT.value,
                "message": "Failed to instantiate plugin",
                "plugin_path": str(plugin_path)
            }

        # Register plugin with system
        if not self.register_plugin_with_system(manifest.name, instance, manifest):
            return {
                "status": PluginLoadStatus.FAILED_IMPORT.value,
                "message": "Failed to register plugin with system",
                "plugin_path": str(plugin_path)
            }

        return {
            "status": PluginLoadStatus.SUCCESS.value,
            "message": f"Plugin {manifest.name} loaded successfully",
            "plugin_name": manifest.name,
            "plugin_path": str(plugin_path),
            "manifest": manifest.to_dict()
        }

    def load_all_plugins(self) -> Dict[str, Any]:
        """
        Load all discoverable plugins.

        Returns:
            Dictionary with loading statistics
        """
        plugin_paths = self.discover_plugins()

        results = {
            "successful": [],
            "failed": [],
            "skipped": []
        }

        for plugin_path in plugin_paths:
            # Check if plugin is enabled in manifest
            manifest = self.load_plugin_manifest(plugin_path)
            if manifest and not manifest.enabled:
                results["skipped"].append({
                    "plugin_path": str(plugin_path),
                    "reason": "Plugin is disabled in manifest"
                })
                continue

            # Attempt to load the plugin
            result = self.load_plugin(plugin_path)

            if result["status"] == PluginLoadStatus.SUCCESS.value:
                results["successful"].append(result)
            else:
                results["failed"].append(result)

        return {
            "total_discovered": len(plugin_paths),
            "successful_loads": len(results["successful"]),
            "failed_loads": len(results["failed"]),
            "skipped_loads": len(results["skipped"]),
            "details": results
        }

    def get_loaded_plugins(self) -> Dict[str, Any]:
        """
        Get information about all loaded plugins.

        Returns:
            Dictionary with plugin information
        """
        plugin_info = {}

        for name, instance in self.plugin_instances.items():
            manifest = self.plugin_manifests.get(name)
            plugin_info[name] = {
                "name": name,
                "instance_type": type(instance).__name__,
                "manifest": manifest.to_dict() if manifest else None,
                "has_initialize": hasattr(instance, 'initialize'),
                "has_shutdown": hasattr(instance, 'shutdown'),
                "methods": [method for method in dir(instance) if not method.startswith('_')]
            }

        return plugin_info

    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin by name.

        Args:
            plugin_name: Name of the plugin to unload

        Returns:
            True if unloading was successful, False otherwise
        """
        try:
            # Call shutdown method if available
            if plugin_name in self.plugin_instances:
                instance = self.plugin_instances[plugin_name]
                if hasattr(instance, 'shutdown'):
                    instance.shutdown()

            # Remove from loaded plugins
            if plugin_name in self.loaded_plugins:
                del self.loaded_plugins[plugin_name]

            if plugin_name in self.plugin_instances:
                del self.plugin_instances[plugin_name]

            if plugin_name in self.plugin_manifests:
                del self.plugin_manifests[plugin_name]

            # Remove from database
            try:
                plugin_record = Plugin.get_by_name(plugin_name)
                if plugin_record:
                    plugin_record.delete()
            except Exception as e:
                self.logger.warning(f"Could not remove plugin {plugin_name} from database: {e}")

            self.logger.info(f"Plugin {plugin_name} unloaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unload plugin {plugin_name}: {e}")
            return False

    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """
        Get a loaded plugin instance by name.

        Args:
            plugin_name: Name of the plugin to retrieve

        Returns:
            Plugin instance if found and loaded, None otherwise
        """
        return self.loaded_plugins.get(plugin_name)

    def initialize_loaded_plugins(self):
        """Call initialize method on all loaded plugins that have it."""
        for name, instance in self.plugin_instances.items():
            try:
                if hasattr(instance, 'initialize'):
                    instance.initialize()
                    self.logger.info(f"Initialized plugin: {name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize plugin {name}: {e}")


class PluginRegistry:
    """Singleton registry for managing plugins across the system."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PluginRegistry, cls).__new__(cls)
            cls._instance.loader = PluginLoader()
        return cls._instance

    def load_all_plugins(self):
        """Load all available plugins."""
        return self.loader.load_all_plugins()

    def get_plugin(self, plugin_name: str):
        """Get a plugin instance by name."""
        return self.loader.get_plugin(plugin_name)

    def get_loaded_plugins(self):
        """Get information about all loaded plugins."""
        return self.loader.get_loaded_plugins()

    def initialize_loaded_plugins(self):
        """Initialize all loaded plugins."""
        self.loader.initialize_loaded_plugins()


# Global plugin registry instance
plugin_registry = PluginRegistry()


# Convenience functions
def load_all_plugins():
    """Load all available plugins."""
    return plugin_registry.load_all_plugins()


def get_plugin(plugin_name: str):
    """Get a plugin instance by name."""
    return plugin_registry.get_plugin(plugin_name)


def get_loaded_plugins():
    """Get information about all loaded plugins."""
    return plugin_registry.get_loaded_plugins()