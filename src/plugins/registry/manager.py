"""
Plugin activation/deactivation service for the x-agent2 AI assistant system.

This module handles the activation and deactivation of plugins that have been
registered in the system.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import logging
from enum import Enum

from src.db.models.plugin import Plugin as PluginModel
from src.plugins.registry.registry import PluginRegistryService
from src.plugins.registry.loader import PluginLoader
from src.agent_core.config.config_service import get_config


class ActivationStatus(Enum):
    """Status of plugin activation operations."""
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ALREADY_ACTIVE = "already_active"
    ALREADY_INACTIVE = "already_inactive"
    DEPENDENCY_ERROR = "dependency_error"
    PLUGIN_NOT_FOUND = "plugin_not_found"
    INITIALIZATION_ERROR = "initialization_error"
    SHUTDOWN_ERROR = "shutdown_error"


class PluginActivationService:
    """Service class for managing plugin activation and deactivation."""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Initialize supporting services
        self.registry_service = PluginRegistryService()
        self.loader = PluginLoader()

        # Track active plugins
        self.active_plugins: Dict[str, Dict[str, Any]] = {}

    async def activate_plugin(self, plugin_name: str, validate_dependencies: bool = True) -> Dict[str, Any]:
        """
        Activate a registered plugin.

        Args:
            plugin_name: Name of the plugin to activate
            validate_dependencies: Whether to validate dependencies before activation

        Returns:
            Dictionary with activation results
        """
        try:
            # Check if plugin exists in registry
            plugin_info = await self.registry_service.get_plugin_info(plugin_name)
            if not plugin_info:
                return {
                    "status": ActivationStatus.PLUGIN_NOT_FOUND.value,
                    "message": f"Plugin {plugin_name} is not registered",
                    "plugin_name": plugin_name
                }

            # Check if plugin is already active
            if plugin_name in self.active_plugins:
                return {
                    "status": ActivationStatus.ALREADY_ACTIVE.value,
                    "message": f"Plugin {plugin_name} is already active",
                    "plugin_name": plugin_name
                }

            # Check if plugin is enabled in registry
            if not plugin_info.get("enabled", False):
                return {
                    "status": "disabled",
                    "message": f"Plugin {plugin_name} is disabled and cannot be activated",
                    "plugin_name": plugin_name
                }

            # Validate dependencies if requested
            if validate_dependencies:
                deps_result = await self._validate_dependencies(plugin_name)
                if not deps_result["valid"]:
                    return {
                        "status": ActivationStatus.DEPENDENCY_ERROR.value,
                        "message": f"Plugin {plugin_name} has unmet dependencies: {deps_result['missing']}",
                        "missing_dependencies": deps_result["missing"],
                        "plugin_name": plugin_name
                    }

            # Get the plugin instance from loader
            plugin_instance = self.loader.get_plugin(plugin_name)
            if not plugin_instance:
                # Try to load it if not already loaded
                # This is a simplified approach - in reality, you might want to load from stored path
                return {
                    "status": "not_loaded",
                    "message": f"Plugin {plugin_name} is registered but not loaded in memory",
                    "plugin_name": plugin_name
                }

            # Try to initialize the plugin
            try:
                if hasattr(plugin_instance, 'initialize'):
                    plugin_instance.initialize()
            except Exception as e:
                self.logger.error(f"Error initializing plugin {plugin_name}: {e}")
                return {
                    "status": ActivationStatus.INITIALIZATION_ERROR.value,
                    "message": f"Plugin {plugin_name} initialization failed: {str(e)}",
                    "plugin_name": plugin_name,
                    "error": str(e)
                }

            # Add to active plugins
            self.active_plugins[plugin_name] = {
                "instance": plugin_instance,
                "activated_at": datetime.utcnow().isoformat(),
                "dependencies_met": True,
                "initialized": True
            }

            # Update plugin status in database
            try:
                plugin_record = await PluginModel.get_by_name(plugin_name)
                if plugin_record:
                    await plugin_record.update(
                        last_activated_at=datetime.utcnow(),
                        is_active=True
                    )
            except Exception as e:
                self.logger.warning(f"Could not update plugin activation status in DB: {e}")

            self.logger.info(f"Plugin {plugin_name} activated successfully")

            return {
                "status": ActivationStatus.ACTIVATED.value,
                "message": f"Plugin {plugin_name} activated successfully",
                "plugin_name": plugin_name,
                "activated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error activating plugin {plugin_name}: {e}")
            return {
                "status": "error",
                "message": f"Error activating plugin: {str(e)}",
                "plugin_name": plugin_name
            }

    async def deactivate_plugin(self, plugin_name: str, check_dependents: bool = True) -> Dict[str, Any]:
        """
        Deactivate an active plugin.

        Args:
            plugin_name: Name of the plugin to deactivate
            check_dependents: Whether to check if other plugins depend on this one

        Returns:
            Dictionary with deactivation results
        """
        try:
            # Check if plugin is active
            if plugin_name not in self.active_plugins:
                return {
                    "status": ActivationStatus.ALREADY_INACTIVE.value,
                    "message": f"Plugin {plugin_name} is not currently active",
                    "plugin_name": plugin_name
                }

            # Check if other plugins depend on this one
            if check_dependents:
                dependent_plugins = await self.registry_service.get_dependent_plugins(plugin_name)
                active_dependents = [dp for dp in dependent_plugins if dp in self.active_plugins]

                if active_dependents:
                    return {
                        "status": "dependent_plugins_active",
                        "message": f"Cannot deactivate {plugin_name} because the following active plugins depend on it: {', '.join(active_dependents)}",
                        "dependent_plugins": active_dependents,
                        "plugin_name": plugin_name
                    }

            # Get plugin instance
            plugin_data = self.active_plugins[plugin_name]
            plugin_instance = plugin_data["instance"]

            # Try to shutdown the plugin gracefully
            try:
                if hasattr(plugin_instance, 'shutdown'):
                    plugin_instance.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down plugin {plugin_name}: {e}")
                # Continue with deactivation even if shutdown fails

            # Remove from active plugins
            del self.active_plugins[plugin_name]

            # Update plugin status in database
            try:
                plugin_record = await PluginModel.get_by_name(plugin_name)
                if plugin_record:
                    await plugin_record.update(
                        last_deactivated_at=datetime.utcnow(),
                        is_active=False
                    )
            except Exception as e:
                self.logger.warning(f"Could not update plugin deactivation status in DB: {e}")

            self.logger.info(f"Plugin {plugin_name} deactivated successfully")

            return {
                "status": ActivationStatus.DEACTIVATED.value,
                "message": f"Plugin {plugin_name} deactivated successfully",
                "plugin_name": plugin_name,
                "deactivated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error deactivating plugin {plugin_name}: {e}")
            return {
                "status": "error",
                "message": f"Error deactivating plugin: {str(e)}",
                "plugin_name": plugin_name
            }

    async def activate_multiple_plugins(self, plugin_names: List[str], parallel: bool = True) -> Dict[str, Any]:
        """
        Activate multiple plugins.

        Args:
            plugin_names: List of plugin names to activate
            parallel: Whether to activate plugins in parallel

        Returns:
            Dictionary with activation results
        """
        results = {
            "successful_activations": [],
            "failed_activations": [],
            "skipped_activations": []
        }

        if parallel:
            # Run activations in parallel
            tasks = [self.activate_plugin(name) for name in plugin_names]
            activation_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(activation_results):
                plugin_name = plugin_names[i]

                if isinstance(result, Exception):
                    results["failed_activations"].append({
                        "plugin_name": plugin_name,
                        "error": str(result),
                        "status": "exception"
                    })
                elif result["status"] == ActivationStatus.ACTIVATED.value:
                    results["successful_activations"].append(result)
                elif result["status"] == ActivationStatus.ALREADY_ACTIVE.value:
                    results["skipped_activations"].append(result)
                else:
                    results["failed_activations"].append(result)
        else:
            # Run activations sequentially
            for plugin_name in plugin_names:
                result = await self.activate_plugin(plugin_name)

                if result["status"] == ActivationStatus.ACTIVATED.value:
                    results["successful_activations"].append(result)
                elif result["status"] == ActivationStatus.ALREADY_ACTIVE.value:
                    results["skipped_activations"].append(result)
                else:
                    results["failed_activations"].append(result)

        return {
            "total_requested": len(plugin_names),
            "successful": len(results["successful_activations"]),
            "failed": len(results["failed_activations"]),
            "skipped": len(results["skipped_activations"]),
            "results": results
        }

    async def deactivate_multiple_plugins(self, plugin_names: List[str], parallel: bool = True) -> Dict[str, Any]:
        """
        Deactivate multiple plugins.

        Args:
            plugin_names: List of plugin names to deactivate
            parallel: Whether to deactivate plugins in parallel

        Returns:
            Dictionary with deactivation results
        """
        results = {
            "successful_deactivations": [],
            "failed_deactivations": [],
            "skipped_deactivations": []
        }

        if parallel:
            # Run deactivations in parallel
            tasks = [self.deactivate_plugin(name) for name in plugin_names]
            deactivation_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(deactivation_results):
                plugin_name = plugin_names[i]

                if isinstance(result, Exception):
                    results["failed_deactivations"].append({
                        "plugin_name": plugin_name,
                        "error": str(result),
                        "status": "exception"
                    })
                elif result["status"] == ActivationStatus.DEACTIVATED.value:
                    results["successful_deactivations"].append(result)
                elif result["status"] == ActivationStatus.ALREADY_INACTIVE.value:
                    results["skipped_deactivations"].append(result)
                else:
                    results["failed_deactivations"].append(result)
        else:
            # Run deactivations sequentially, in reverse dependency order to prevent issues
            ordered_plugins = await self.registry_service.get_plugin_activation_order(plugin_names)
            ordered_plugins.reverse()  # Reverse to deactivate dependents first

            for plugin_name in ordered_plugins:
                result = await self.deactivate_plugin(plugin_name)

                if result["status"] == ActivationStatus.DEACTIVATED.value:
                    results["successful_deactivations"].append(result)
                elif result["status"] == ActivationStatus.ALREADY_INACTIVE.value:
                    results["skipped_deactivations"].append(result)
                else:
                    results["failed_deactivations"].append(result)

        return {
            "total_requested": len(plugin_names),
            "successful": len(results["successful_deactivations"]),
            "failed": len(results["failed_deactivations"]),
            "skipped": len(results["skipped_deactivations"]),
            "results": results
        }

    async def get_active_plugins(self) -> List[Dict[str, Any]]:
        """
        Get a list of all active plugins.

        Returns:
            List of active plugin information
        """
        active_plugin_list = []

        for plugin_name, plugin_data in self.active_plugins.items():
            # Get additional info from registry
            plugin_info = await self.registry_service.get_plugin_info(plugin_name)

            active_plugin_list.append({
                "name": plugin_name,
                "activated_at": plugin_data["activated_at"],
                "initialized": plugin_data.get("initialized", False),
                "dependencies_met": plugin_data.get("dependencies_met", True),
                "description": plugin_info.get("description") if plugin_info else "No description available",
                "version": plugin_info.get("version") if plugin_info else "Unknown",
                "author": plugin_info.get("author") if plugin_info else "Unknown"
            })

        return active_plugin_list

    async def is_plugin_active(self, plugin_name: str) -> bool:
        """
        Check if a plugin is currently active.

        Args:
            plugin_name: Name of the plugin to check

        Returns:
            True if active, False otherwise
        """
        return plugin_name in self.active_plugins

    async def _validate_dependencies(self, plugin_name: str) -> Dict[str, Any]:
        """
        Validate that all dependencies for a plugin are met and active.

        Args:
            plugin_name: Name of the plugin to validate dependencies for

        Returns:
            Dictionary with validation results
        """
        # Get plugin dependencies
        dependencies = await self.registry_service.get_plugin_dependencies(plugin_name)

        missing_deps = []
        inactive_deps = []

        for dep_name in dependencies:
            # Check if dependency is registered
            if not await self.registry_service.is_plugin_registered(dep_name):
                missing_deps.append(dep_name)
            # Check if dependency is active
            elif not await self.is_plugin_active(dep_name):
                inactive_deps.append(dep_name)

        return {
            "valid": len(missing_deps) == 0 and len(inactive_deps) == 0,
            "missing": missing_deps,
            "inactive": inactive_deps,
            "all_dependencies": dependencies
        }

    async def activate_with_dependencies(self, plugin_name: str) -> Dict[str, Any]:
        """
        Activate a plugin and all its dependencies recursively.

        Args:
            plugin_name: Name of the plugin to activate

        Returns:
            Dictionary with activation results
        """
        try:
            # Get dependency order
            all_plugins_to_activate = await self.registry_service.get_plugin_activation_order([plugin_name])

            # Activate in dependency order
            results = await self.activate_multiple_plugins(all_plugins_to_activate, parallel=False)

            return {
                "status": "completed",
                "message": f"Activated {plugin_name} and its dependencies",
                "plugin_name": plugin_name,
                "activation_results": results
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error activating plugin with dependencies: {str(e)}",
                "plugin_name": plugin_name
            }

    async def get_activation_requirements(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get all requirements for activating a plugin (dependencies and their status).

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dictionary with activation requirements
        """
        try:
            # Get plugin info
            plugin_info = await self.registry_service.get_plugin_info(plugin_name)
            if not plugin_info:
                return {
                    "plugin_exists": False,
                    "requirements": [],
                    "can_activate": False,
                    "reason": "Plugin not registered"
                }

            # Get dependencies
            dependencies = await self.registry_service.get_plugin_dependencies(plugin_name)

            requirements = []
            all_satisfied = True
            reason = ""

            for dep_name in dependencies:
                is_registered = await self.registry_service.is_plugin_registered(dep_name)
                is_active = await self.is_plugin_active(dep_name)

                req_status = {
                    "name": dep_name,
                    "registered": is_registered,
                    "active": is_active,
                    "can_activate": is_registered and not is_active
                }

                requirements.append(req_status)

                if not is_registered:
                    all_satisfied = False
                    if not reason:
                        reason = f"Dependency '{dep_name}' not registered"
                elif not is_active:
                    all_satisfied = False
                    if not reason:
                        reason = f"Dependency '{dep_name}' not active"

            return {
                "plugin_exists": True,
                "requirements": requirements,
                "can_activate": all_satisfied,
                "reason": reason if not all_satisfied else "All requirements satisfied"
            }
        except Exception as e:
            return {
                "plugin_exists": False,
                "requirements": [],
                "can_activate": False,
                "reason": f"Error checking requirements: {str(e)}"
            }

    async def refresh_active_plugins(self):
        """
        Refresh the active plugins list by checking against the database.
        """
        try:
            # Get currently active plugins from database
            all_plugins = await PluginModel.get_all()
            db_active_plugins = [p.name for p in all_plugins if p.is_active]

            # Find plugins that are active in DB but not in memory
            for plugin_name in db_active_plugins:
                if plugin_name not in self.active_plugins:
                    # Attempt to activate it
                    await self.activate_plugin(plugin_name)

            # Find plugins that are active in memory but not in DB
            for plugin_name in list(self.active_plugins.keys()):
                plugin_record = await PluginModel.get_by_name(plugin_name)
                if not plugin_record or not plugin_record.is_active:
                    # Remove from active if not marked active in DB
                    del self.active_plugins[plugin_name]

            return {
                "status": "success",
                "message": "Active plugins list refreshed",
                "current_active_count": len(self.active_plugins)
            }
        except Exception as e:
            self.logger.error(f"Error refreshing active plugins: {e}")
            return {
                "status": "error",
                "message": f"Error refreshing active plugins: {str(e)}"
            }

    async def toggle_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """
        Toggle a plugin's activation state.

        Args:
            plugin_name: Name of the plugin to toggle

        Returns:
            Dictionary with toggle results
        """
        is_active = await self.is_plugin_active(plugin_name)

        if is_active:
            return await self.deactivate_plugin(plugin_name)
        else:
            return await self.activate_plugin(plugin_name)


class PluginStateManager:
    """Manages the state of plugins across application restarts."""

    def __init__(self, activation_service: PluginActivationService):
        self.activation_service = activation_service
        self.logger = logging.getLogger(__name__)

    async def restore_plugin_state(self) -> Dict[str, Any]:
        """
        Restore plugin activation state from database.

        Returns:
            Dictionary with restoration results
        """
        try:
            # Get all plugins that were active in the database
            all_plugins = await PluginModel.get_all()
            active_plugins = [p for p in all_plugins if p.is_active and p.enabled]

            plugin_names = [p.name for p in active_plugins]
            results = await self.activation_service.activate_multiple_plugins(
                plugin_names,
                parallel=True
            )

            return {
                "status": "completed",
                "message": f"Restored state for {len(plugin_names)} plugins",
                "requested_count": len(plugin_names),
                "successful": results["successful"],
                "failed": results["failed"]
            }
        except Exception as e:
            self.logger.error(f"Error restoring plugin state: {e}")
            return {
                "status": "error",
                "message": f"Error restoring plugin state: {str(e)}"
            }

    async def save_plugin_state(self) -> Dict[str, Any]:
        """
        Save current plugin activation state to database.

        Returns:
            Dictionary with save results
        """
        try:
            active_plugins = await self.activation_service.get_active_plugins()

            # Update each active plugin's state in the database
            updated_count = 0
            for plugin_info in active_plugins:
                plugin_name = plugin_info["name"]
                try:
                    plugin_record = await PluginModel.get_by_name(plugin_name)
                    if plugin_record:
                        await plugin_record.update(is_active=True)
                        updated_count += 1
                except Exception as e:
                    self.logger.error(f"Error saving state for plugin {plugin_name}: {e}")

            return {
                "status": "completed",
                "message": f"Saved state for {updated_count} active plugins",
                "saved_count": updated_count
            }
        except Exception as e:
            self.logger.error(f"Error saving plugin state: {e}")
            return {
                "status": "error",
                "message": f"Error saving plugin state: {str(e)}"
            }


# Global instances
plugin_activation_service = PluginActivationService()
plugin_state_manager = PluginStateManager(plugin_activation_service)


# Convenience functions
async def activate_plugin(plugin_name: str) -> Dict[str, Any]:
    """Activate a registered plugin."""
    return await plugin_activation_service.activate_plugin(plugin_name)


async def deactivate_plugin(plugin_name: str) -> Dict[str, Any]:
    """Deactivate an active plugin."""
    return await plugin_activation_service.deactivate_plugin(plugin_name)


async def activate_multiple_plugins(plugin_names: List[str], parallel: bool = True) -> Dict[str, Any]:
    """Activate multiple plugins."""
    return await plugin_activation_service.activate_multiple_plugins(plugin_names, parallel)


async def deactivate_multiple_plugins(plugin_names: List[str], parallel: bool = True) -> Dict[str, Any]:
    """Deactivate multiple plugins."""
    return await plugin_activation_service.deactivate_multiple_plugins(plugin_names, parallel)


async def get_active_plugins() -> List[Dict[str, Any]]:
    """Get a list of all active plugins."""
    return await plugin_activation_service.get_active_plugins()


async def is_plugin_active(plugin_name: str) -> bool:
    """Check if a plugin is currently active."""
    return await plugin_activation_service.is_plugin_active(plugin_name)


async def get_activation_requirements(plugin_name: str) -> Dict[str, Any]:
    """Get activation requirements for a plugin."""
    return await plugin_activation_service.get_activation_requirements(plugin_name)