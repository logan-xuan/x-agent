"""
Plugin registry service for the x-agent2 AI assistant system.

This module handles the registration, discovery, and management of plugins
within the system.
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import asyncio
import logging
from pathlib import Path

from src.db.models.plugin import Plugin as PluginModel
from src.plugins.registry.loader import PluginLoader, PluginRegistry
from src.plugins.registry.manifest_parser import PluginManifestManager
from src.plugins.security.validator import PluginValidator
from src.agent_core.config.config_service import get_config


class RegistrationStatus(Enum):
    """Status of plugin registration operations."""
    SUCCESS = "success"
    FAILED_VALIDATION = "failed_validation"
    FAILED_LOAD = "failed_load"
    ALREADY_REGISTERED = "already_registered"
    MISSING_DEPENDENCY = "missing_dependency"


class PluginRegistryService:
    """Service class for managing plugin registration and discovery."""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Initialize supporting services
        self.loader = PluginLoader()
        self.manifest_manager = PluginManifestManager()
        self.validator = PluginValidator()

        # Plugin state tracking
        self.registered_plugins: Dict[str, Dict[str, Any]] = {}
        self.plugin_dependencies: Dict[str, List[str]] = {}
        self.dependency_graph: Dict[str, List[str]] = {}  # plugin -> list of plugins that depend on it

    async def register_plugin(self, plugin_path: str) -> Dict[str, Any]:
        """
        Register a plugin from the specified path.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with registration results
        """
        plugin_path = Path(plugin_path)

        try:
            # Step 1: Validate the plugin
            validation_result = self.validator.validate(plugin_path)
            if validation_result["overall_result"] == "failed":
                return {
                    "status": RegistrationStatus.FAILED_VALIDATION.value,
                    "message": "Plugin validation failed",
                    "validation_result": validation_result,
                    "plugin_path": str(plugin_path)
                }

            # Step 2: Parse the manifest
            manifest_result = self.manifest_manager.load_and_validate_manifest(
                plugin_path / "plugin.json",
                self.config.version
            )

            if not manifest_result["is_valid"]:
                return {
                    "status": RegistrationStatus.FAILED_VALIDATION.value,
                    "message": "Plugin manifest validation failed",
                    "validation_errors": manifest_result.get("error", "Unknown error"),
                    "plugin_path": str(plugin_path)
                }

            plugin_name = manifest_result["manifest"]["name"]

            # Step 3: Check if plugin is already registered
            if await self.is_plugin_registered(plugin_name):
                return {
                    "status": RegistrationStatus.ALREADY_REGISTERED.value,
                    "message": f"Plugin {plugin_name} is already registered",
                    "plugin_name": plugin_name
                }

            # Step 4: Check dependencies
            missing_deps = await self._check_missing_dependencies(manifest_result["manifest"]["dependencies"])
            if missing_deps:
                return {
                    "status": RegistrationStatus.MISSING_DEPENDENCY.value,
                    "message": f"Plugin {plugin_name} has missing dependencies: {', '.join(missing_deps)}",
                    "missing_dependencies": missing_deps,
                    "plugin_name": plugin_name
                }

            # Step 5: Load the plugin using the loader
            load_result = self.loader.load_plugin(plugin_path)
            if load_result["status"] != "success":
                return {
                    "status": RegistrationStatus.FAILED_LOAD.value,
                    "message": f"Failed to load plugin: {load_result['message']}",
                    "load_result": load_result,
                    "plugin_name": plugin_name
                }

            # Step 6: Create plugin record in database
            plugin_record = PluginModel(
                id=None,  # Will be auto-generated
                name=plugin_name,
                version=manifest_result["manifest"]["version"],
                description=manifest_result["manifest"]["description"],
                author=manifest_result["manifest"]["author"],
                license=manifest_result["manifest"]["license"],
                repository=manifest_result["manifest"]["repository"],
                enabled=manifest_result["manifest"]["enabled"],
                metadata=manifest_result["manifest"],
                installed_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )

            await plugin_record.save()

            # Step 7: Update internal tracking
            self.registered_plugins[plugin_name] = {
                "path": str(plugin_path),
                "manifest": manifest_result["manifest"],
                "registered_at": datetime.utcnow().isoformat(),
                "validation_result": validation_result
            }

            # Track dependencies
            self.plugin_dependencies[plugin_name] = manifest_result["manifest"]["dependencies"]

            # Update dependency graph
            for dep in manifest_result["manifest"]["dependencies"]:
                if dep not in self.dependency_graph:
                    self.dependency_graph[dep] = []
                self.dependency_graph[dep].append(plugin_name)

            self.logger.info(f"Plugin {plugin_name} registered successfully")

            return {
                "status": RegistrationStatus.SUCCESS.value,
                "message": f"Plugin {plugin_name} registered successfully",
                "plugin_name": plugin_name,
                "plugin_path": str(plugin_path),
                "validation_result": validation_result,
                "plugin_record_id": plugin_record.id
            }
        except Exception as e:
            self.logger.error(f"Error registering plugin {plugin_path}: {e}")
            return {
                "status": RegistrationStatus.FAILED_LOAD.value,
                "message": f"Error registering plugin: {str(e)}",
                "plugin_path": str(plugin_path)
            }

    async def unregister_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """
        Unregister a plugin by name.

        Args:
            plugin_name: Name of the plugin to unregister

        Returns:
            Dictionary with unregistration results
        """
        try:
            # Check if plugin is registered
            if not await self.is_plugin_registered(plugin_name):
                return {
                    "status": "not_found",
                    "message": f"Plugin {plugin_name} is not registered",
                    "plugin_name": plugin_name
                }

            # Check if other plugins depend on this one
            dependent_plugins = self.dependency_graph.get(plugin_name, [])
            if dependent_plugins:
                return {
                    "status": "dependency_conflict",
                    "message": f"Cannot unregister {plugin_name} because the following plugins depend on it: {', '.join(dependent_plugins)}",
                    "dependent_plugins": dependent_plugins,
                    "plugin_name": plugin_name
                }

            # Remove from database
            plugin_record = await PluginModel.get_by_name(plugin_name)
            if plugin_record:
                await plugin_record.delete()

            # Remove from internal tracking
            if plugin_name in self.registered_plugins:
                del self.registered_plugins[plugin_name]

            if plugin_name in self.plugin_dependencies:
                del self.plugin_dependencies[plugin_name]

            # Remove from dependency graph
            for dep, dependents in list(self.dependency_graph.items()):
                if plugin_name in dependents:
                    dependents.remove(plugin_name)
                    if not dependents:  # Clean up empty lists
                        del self.dependency_graph[dep]

            # Unload from the loader
            self.loader.unload_plugin(plugin_name)

            self.logger.info(f"Plugin {plugin_name} unregistered successfully")

            return {
                "status": "success",
                "message": f"Plugin {plugin_name} unregistered successfully",
                "plugin_name": plugin_name
            }
        except Exception as e:
            self.logger.error(f"Error unregistering plugin {plugin_name}: {e}")
            return {
                "status": "error",
                "message": f"Error unregistering plugin: {str(e)}",
                "plugin_name": plugin_name
            }

    async def is_plugin_registered(self, plugin_name: str) -> bool:
        """
        Check if a plugin is registered.

        Args:
            plugin_name: Name of the plugin to check

        Returns:
            True if registered, False otherwise
        """
        try:
            # Check internal registry
            is_internal = plugin_name in self.registered_plugins

            # Also check database
            try:
                plugin_record = await PluginModel.get_by_name(plugin_name)
                is_database = plugin_record is not None
            except:
                is_database = False  # If DB query fails, assume not registered

            return is_internal or is_database
        except:
            return False

    async def get_registered_plugins(self) -> List[Dict[str, Any]]:
        """
        Get a list of all registered plugins.

        Returns:
            List of registered plugin information
        """
        try:
            # Get plugins from the database
            db_plugins = await PluginModel.get_all()

            # Format the response
            plugins_info = []
            for db_plugin in db_plugins:
                plugins_info.append({
                    "id": db_plugin.id,
                    "name": db_plugin.name,
                    "version": db_plugin.version,
                    "description": db_plugin.description,
                    "author": db_plugin.author,
                    "license": db_plugin.license,
                    "repository": db_plugin.repository,
                    "enabled": db_plugin.enabled,
                    "installed_at": db_plugin.installed_at.isoformat() if db_plugin.installed_at else None,
                    "last_updated": db_plugin.last_updated.isoformat() if db_plugin.last_updated else None,
                    "metadata": db_plugin.metadata
                })

            return plugins_info
        except Exception as e:
            self.logger.error(f"Error getting registered plugins: {e}")
            return []

    async def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific registered plugin.

        Args:
            plugin_name: Name of the plugin to get info for

        Returns:
            Plugin information if found, None otherwise
        """
        try:
            # Check internal registry first
            if plugin_name in self.registered_plugins:
                return self.registered_plugins[plugin_name]

            # Then check database
            plugin_record = await PluginModel.get_by_name(plugin_name)
            if plugin_record:
                return {
                    "id": plugin_record.id,
                    "name": plugin_record.name,
                    "version": plugin_record.version,
                    "description": plugin_record.description,
                    "author": plugin_record.author,
                    "license": plugin_record.license,
                    "repository": plugin_record.repository,
                    "enabled": plugin_record.enabled,
                    "installed_at": plugin_record.installed_at.isoformat() if plugin_record.installed_at else None,
                    "last_updated": plugin_record.last_updated.isoformat() if plugin_record.last_updated else None,
                    "metadata": plugin_record.metadata,
                    "path": self.registered_plugins.get(plugin_name, {}).get("path", "unknown")
                }

            return None
        except Exception as e:
            self.logger.error(f"Error getting plugin info for {plugin_name}: {e}")
            return None

    async def enable_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """
        Enable a registered plugin.

        Args:
            plugin_name: Name of the plugin to enable

        Returns:
            Dictionary with operation results
        """
        try:
            # Get plugin from database
            plugin_record = await PluginModel.get_by_name(plugin_name)
            if not plugin_record:
                return {
                    "status": "not_found",
                    "message": f"Plugin {plugin_name} is not registered",
                    "plugin_name": plugin_name
                }

            if plugin_record.enabled:
                return {
                    "status": "already_enabled",
                    "message": f"Plugin {plugin_name} is already enabled",
                    "plugin_name": plugin_name
                }

            # Update in database
            await plugin_record.update(enabled=True, last_updated=datetime.utcnow())

            # Update internal registry
            if plugin_name in self.registered_plugins:
                self.registered_plugins[plugin_name]["metadata"]["enabled"] = True

            return {
                "status": "success",
                "message": f"Plugin {plugin_name} enabled successfully",
                "plugin_name": plugin_name
            }
        except Exception as e:
            self.logger.error(f"Error enabling plugin {plugin_name}: {e}")
            return {
                "status": "error",
                "message": f"Error enabling plugin: {str(e)}",
                "plugin_name": plugin_name
            }

    async def disable_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """
        Disable a registered plugin.

        Args:
            plugin_name: Name of the plugin to disable

        Returns:
            Dictionary with operation results
        """
        try:
            # Get plugin from database
            plugin_record = await PluginModel.get_by_name(plugin_name)
            if not plugin_record:
                return {
                    "status": "not_found",
                    "message": f"Plugin {plugin_name} is not registered",
                    "plugin_name": plugin_name
                }

            if not plugin_record.enabled:
                return {
                    "status": "already_disabled",
                    "message": f"Plugin {plugin_name} is already disabled",
                    "plugin_name": plugin_name
                }

            # Check if other plugins depend on this one
            dependent_plugins = self.dependency_graph.get(plugin_name, [])
            if dependent_plugins:
                return {
                    "status": "dependency_conflict",
                    "message": f"Cannot disable {plugin_name} because the following plugins depend on it: {', '.join(dependent_plugins)}",
                    "dependent_plugins": dependent_plugins,
                    "plugin_name": plugin_name
                }

            # Update in database
            await plugin_record.update(enabled=False, last_updated=datetime.utcnow())

            # Update internal registry
            if plugin_name in self.registered_plugins:
                self.registered_plugins[plugin_name]["metadata"]["enabled"] = False

            return {
                "status": "success",
                "message": f"Plugin {plugin_name} disabled successfully",
                "plugin_name": plugin_name
            }
        except Exception as e:
            self.logger.error(f"Error disabling plugin {plugin_name}: {e}")
            return {
                "status": "error",
                "message": f"Error disabling plugin: {str(e)}",
                "plugin_name": plugin_name
            }

    async def _check_missing_dependencies(self, dependencies: List[str]) -> List[str]:
        """
        Check if all required dependencies are registered.

        Args:
            dependencies: List of dependency names

        Returns:
            List of missing dependencies
        """
        missing = []
        for dep in dependencies:
            if not await self.is_plugin_registered(dep):
                missing.append(dep)
        return missing

    async def get_plugin_dependencies(self, plugin_name: str) -> List[str]:
        """
        Get the dependencies of a plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            List of dependency names
        """
        try:
            # First check internal tracking
            if plugin_name in self.plugin_dependencies:
                return self.plugin_dependencies[plugin_name]

            # Then check database
            plugin_record = await PluginModel.get_by_name(plugin_name)
            if plugin_record and plugin_record.metadata:
                return plugin_record.metadata.get("dependencies", [])

            return []
        except Exception:
            return []

    async def get_dependent_plugins(self, plugin_name: str) -> List[str]:
        """
        Get all plugins that depend on the specified plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            List of plugin names that depend on this plugin
        """
        try:
            return self.dependency_graph.get(plugin_name, [])
        except Exception:
            return []

    async def get_plugin_activation_order(self, plugin_names: List[str]) -> List[str]:
        """
        Get the proper activation order for plugins considering dependencies.

        Args:
            plugin_names: List of plugin names to activate

        Returns:
            List of plugin names in activation order
        """
        # This is a simplified implementation of topological sort
        # In a real implementation, you'd want a more robust algorithm

        activation_order = []
        visited = set()

        def visit(plugin):
            if plugin in visited:
                return
            if plugin not in plugin_names:
                return

            visited.add(plugin)

            # Visit dependencies first
            for dep in await self.get_plugin_dependencies(plugin):
                if await self.is_plugin_registered(dep):
                    visit(dep)

            # Then visit this plugin
            if plugin not in activation_order:
                activation_order.append(plugin)

        for plugin in plugin_names:
            visit(plugin)

        return activation_order

    async def register_plugins_from_directory(self, directory_path: str) -> Dict[str, Any]:
        """
        Register all plugins found in a directory.

        Args:
            directory_path: Path to the directory containing plugins

        Returns:
            Dictionary with registration statistics
        """
        directory = Path(directory_path)
        if not directory.exists():
            return {
                "status": "error",
                "message": f"Directory {directory_path} does not exist",
                "total_found": 0,
                "total_registered": 0,
                "total_failed": 0
            }

        # Find all plugin directories (directories containing plugin.json)
        plugin_dirs = []
        for item in directory.iterdir():
            if item.is_dir() and (item / "plugin.json").exists():
                plugin_dirs.append(item)

        results = {
            "successful_registrations": [],
            "failed_registrations": [],
            "skipped_registrations": []
        }

        for plugin_dir in plugin_dirs:
            result = await self.register_plugin(str(plugin_dir))

            if result["status"] == RegistrationStatus.SUCCESS.value:
                results["successful_registrations"].append(result)
            elif result["status"] == RegistrationStatus.ALREADY_REGISTERED.value:
                results["skipped_registrations"].append(result)
            else:
                results["failed_registrations"].append(result)

        return {
            "status": "completed",
            "total_found": len(plugin_dirs),
            "total_registered": len(results["successful_registrations"]),
            "total_skipped": len(results["skipped_registrations"]),
            "total_failed": len(results["failed_registrations"]),
            "details": results
        }

    async def refresh_registry(self):
        """
        Refresh the plugin registry by syncing with the database.
        """
        try:
            # Clear internal registry
            self.registered_plugins.clear()

            # Reload from database
            db_plugins = await PluginModel.get_all()
            for db_plugin in db_plugins:
                self.registered_plugins[db_plugin.name] = {
                    "id": db_plugin.id,
                    "name": db_plugin.name,
                    "version": db_plugin.version,
                    "description": db_plugin.description,
                    "author": db_plugin.author,
                    "license": db_plugin.license,
                    "repository": db_plugin.repository,
                    "enabled": db_plugin.enabled,
                    "installed_at": db_plugin.installed_at.isoformat() if db_plugin.installed_at else None,
                    "last_updated": db_plugin.last_updated.isoformat() if db_plugin.last_updated else None,
                    "metadata": db_plugin.metadata
                }

                # Also update dependencies
                deps = db_plugin.metadata.get("dependencies", []) if db_plugin.metadata else []
                self.plugin_dependencies[db_plugin.name] = deps

                # Update dependency graph
                for dep in deps:
                    if dep not in self.dependency_graph:
                        self.dependency_graph[dep] = []
                    self.dependency_graph[dep].append(db_plugin.name)

            return {
                "status": "success",
                "message": "Registry refreshed successfully",
                "plugins_loaded": len(self.registered_plugins)
            }
        except Exception as e:
            self.logger.error(f"Error refreshing registry: {e}")
            return {
                "status": "error",
                "message": f"Error refreshing registry: {str(e)}"
            }


class PluginDiscoveryService:
    """Service for discovering plugins in various locations."""

    def __init__(self, registry_service: PluginRegistryService):
        self.registry_service = registry_service
        self.logger = logging.getLogger(__name__)

    async def discover_plugins_in_path(self, path: str) -> List[Dict[str, Any]]:
        """
        Discover plugins in a specific path.

        Args:
            path: Path to search for plugins

        Returns:
            List of discovered plugin information
        """
        plugin_path = Path(path)
        discovered_plugins = []

        if not plugin_path.exists():
            self.logger.warning(f"Path {path} does not exist for plugin discovery")
            return discovered_plugins

        # Look for plugin.json files in the directory tree
        for manifest_file in plugin_path.rglob("plugin.json"):
            plugin_dir = manifest_file.parent

            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)

                # Validate the manifest has required fields
                required_fields = ["name", "version", "description", "author"]
                if all(field in manifest for field in required_fields):
                    discovered_plugins.append({
                        "name": manifest["name"],
                        "version": manifest["version"],
                        "description": manifest["description"],
                        "author": manifest["author"],
                        "path": str(plugin_dir.absolute()),
                        "manifest_path": str(manifest_file.absolute()),
                        "is_registered": await self.registry_service.is_plugin_registered(manifest["name"]),
                        "dependencies": manifest.get("dependencies", []),
                        "enabled": manifest.get("enabled", True)
                    })
            except Exception as e:
                self.logger.error(f"Error parsing plugin manifest at {manifest_file}: {e}")

        return discovered_plugins

    async def discover_all_plugins(self) -> List[Dict[str, Any]]:
        """
        Discover plugins in standard locations.

        Returns:
            List of all discovered plugins
        """
        standard_paths = [
            "plugins",
            "workspace/custom-skills",
            "workspace/user-plugins",
            self.config.file_storage.upload_directory
        ]

        all_discovered = []
        for path in standard_paths:
            discovered = await self.discover_plugins_in_path(path)
            all_discovered.extend(discovered)

        # Remove duplicates based on name
        seen_names = set()
        unique_discovered = []
        for plugin in all_discovered:
            if plugin["name"] not in seen_names:
                seen_names.add(plugin["name"])
                unique_discovered.append(plugin)

        return unique_discovered


# Global instances
plugin_registry_service = PluginRegistryService()
plugin_discovery_service = PluginDiscoveryService(plugin_registry_service)


# Convenience functions
async def register_plugin(plugin_path: str) -> Dict[str, Any]:
    """Register a plugin from the specified path."""
    return await plugin_registry_service.register_plugin(plugin_path)


async def unregister_plugin(plugin_name: str) -> Dict[str, Any]:
    """Unregister a plugin by name."""
    return await plugin_registry_service.unregister_plugin(plugin_name)


async def get_registered_plugins() -> List[Dict[str, Any]]:
    """Get a list of all registered plugins."""
    return await plugin_registry_service.get_registered_plugins()


async def get_plugin_info(plugin_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a specific registered plugin."""
    return await plugin_registry_service.get_plugin_info(plugin_name)


async def enable_plugin(plugin_name: str) -> Dict[str, Any]:
    """Enable a registered plugin."""
    return await plugin_registry_service.enable_plugin(plugin_name)


async def disable_plugin(plugin_name: str) -> Dict[str, Any]:
    """Disable a registered plugin."""
    return await plugin_registry_service.disable_plugin(plugin_name)


async def get_plugin_dependencies(plugin_name: str) -> List[str]:
    """Get the dependencies of a plugin."""
    return await plugin_registry_service.get_plugin_dependencies(plugin_name)