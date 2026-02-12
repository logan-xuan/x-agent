"""
Plugin API endpoints for the x-agent2 AI assistant system.

This module provides API endpoints for managing plugins including
installation, activation, deactivation, and configuration.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from src.plugins.registry.registry import (
    plugin_registry_service,
    register_plugin,
    get_registered_plugins,
    get_plugin_info,
    enable_plugin,
    disable_plugin
)
from src.plugins.registry.manager import (
    plugin_activation_service,
    activate_plugin,
    deactivate_plugin,
    get_active_plugins,
    is_plugin_active
)
from src.plugins.registry.loader import plugin_registry
from src.agent_core.api_utils.response_handler import (
    APIResponse,
    APIExceptionHandler,
    create_success_response,
    create_error_response
)
from src.agent_core.security.tool_security import authenticate_user


router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("/register")
async def register_new_plugin(
    plugin_path: str,
    expected_hash: Optional[str] = Query(None)
):
    """
    Register a new plugin from the specified path.

    Args:
        plugin_path: Path to the plugin directory
        expected_hash: Expected hash for integrity verification (optional)

    Returns:
        JSON response with registration details
    """
    try:
        result = await register_plugin(plugin_path, expected_hash)

        if result["status"] == "success":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "plugin_path": result["plugin_path"],
                    "validation_result": result["validation_result"],
                    "plugin_record_id": result["plugin_record_id"],
                    "registered_at": datetime.utcnow().isoformat()
                },
                message=result["message"]
            )
        else:
            # Handle different error statuses
            if result["status"] == "failed_validation":
                return create_error_response(
                    message=result["message"],
                    status_code=400,
                    details={"validation_result": result.get("validation_result")}
                )
            elif result["status"] == "already_registered":
                return create_error_response(
                    message=result["message"],
                    status_code=409,  # Conflict
                    details={"plugin_name": result.get("plugin_name")}
                )
            else:
                return create_error_response(
                    message=result["message"],
                    status_code=500,
                    details={"error_details": result}
                )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to register plugin"
        )


@router.get("/")
async def list_plugins(
    include_inactive: bool = Query(True, description="Include inactive plugins in results"),
    include_disabled: bool = Query(True, description="Include disabled plugins in results")
):
    """
    List all registered plugins with their status.

    Args:
        include_inactive: Whether to include inactive plugins
        include_disabled: Whether to include disabled plugins

    Returns:
        JSON response with plugin list
    """
    try:
        # Get all registered plugins
        plugins = await get_registered_plugins()

        # Apply filters
        filtered_plugins = []
        for plugin in plugins:
            should_include = True

            # Check active status if we're excluding inactive
            if not include_inactive and not plugin.get("enabled", True):
                should_include = False

            # Check enabled status if we're excluding disabled
            if not include_disabled and not plugin.get("enabled", True):
                should_include = False

            if should_include:
                # Add active status info
                plugin["is_active"] = await is_plugin_active(plugin["name"])
                filtered_plugins.append(plugin)

        return create_success_response(
            data={
                "plugins": filtered_plugins,
                "total_count": len(filtered_plugins),
                "filters_applied": {
                    "include_inactive": include_inactive,
                    "include_disabled": include_disabled
                }
            },
            message="Plugins retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to list plugins"
        )


@router.get("/{plugin_name}")
async def get_plugin_details(plugin_name: str):
    """
    Get detailed information about a specific plugin.

    Args:
        plugin_name: Name of the plugin to get details for

    Returns:
        JSON response with plugin details
    """
    try:
        plugin_info = await get_plugin_info(plugin_name)

        if not plugin_info:
            return create_error_response(
                message=f"Plugin '{plugin_name}' not found",
                status_code=404
            )

        # Add active status
        plugin_info["is_active"] = await is_plugin_active(plugin_name)

        return create_success_response(
            data=plugin_info,
            message=f"Details for plugin '{plugin_name}' retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to get details for plugin '{plugin_name}'"
        )


@router.post("/{plugin_name}/activate")
async def activate_plugin_endpoint(plugin_name: str):
    """
    Activate a registered plugin.

    Args:
        plugin_name: Name of the plugin to activate

    Returns:
        JSON response with activation result
    """
    try:
        result = await activate_plugin(plugin_name)

        if result["status"] == "activated":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "activated_at": result["activated_at"]
                },
                message=result["message"]
            )
        elif result["status"] == "already_active":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "message": result["message"]
                },
                message="Plugin was already active"
            )
        elif result["status"] == "dependency_error":
            return create_error_response(
                message=result["message"],
                status_code=424,  # Failed Dependency
                details={
                    "missing_dependencies": result.get("missing_dependencies"),
                    "plugin_name": result["plugin_name"]
                }
            )
        elif result["status"] == "disabled":
            return create_error_response(
                message=result["message"],
                status_code=423,  # Locked
                details={"plugin_name": result["plugin_name"]}
            )
        else:
            return create_error_response(
                message=result["message"],
                status_code=500,
                details={"result": result}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to activate plugin '{plugin_name}'"
        )


@router.post("/{plugin_name}/deactivate")
async def deactivate_plugin_endpoint(plugin_name: str):
    """
    Deactivate an active plugin.

    Args:
        plugin_name: Name of the plugin to deactivate

    Returns:
        JSON response with deactivation result
    """
    try:
        result = await deactivate_plugin(plugin_name)

        if result["status"] == "deactivated":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "deactivated_at": result["deactivated_at"]
                },
                message=result["message"]
            )
        elif result["status"] == "already_inactive":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "message": result["message"]
                },
                message="Plugin was already inactive"
            )
        elif result["status"] == "dependent_plugins_active":
            return create_error_response(
                message=result["message"],
                status_code=424,  # Failed Dependency
                details={
                    "dependent_plugins": result.get("dependent_plugins"),
                    "plugin_name": result["plugin_name"]
                }
            )
        else:
            return create_error_response(
                message=result["message"],
                status_code=500,
                details={"result": result}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to deactivate plugin '{plugin_name}'"
        )


@router.post("/{plugin_name}/enable")
async def enable_plugin_endpoint(plugin_name: str):
    """
    Enable a registered plugin (allows activation).

    Args:
        plugin_name: Name of the plugin to enable

    Returns:
        JSON response with enable result
    """
    try:
        result = await enable_plugin(plugin_name)

        if result["status"] == "success":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"]
                },
                message=result["message"]
            )
        elif result["status"] == "already_enabled":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "message": result["message"]
                },
                message="Plugin was already enabled"
            )
        elif result["status"] == "not_found":
            return create_error_response(
                message=result["message"],
                status_code=404,
                details={"plugin_name": result["plugin_name"]}
            )
        else:
            return create_error_response(
                message=result["message"],
                status_code=500,
                details={"result": result}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to enable plugin '{plugin_name}'"
        )


@router.post("/{plugin_name}/disable")
async def disable_plugin_endpoint(plugin_name: str):
    """
    Disable a registered plugin (prevents activation).

    Args:
        plugin_name: Name of the plugin to disable

    Returns:
        JSON response with disable result
    """
    try:
        result = await disable_plugin(plugin_name)

        if result["status"] == "success":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"]
                },
                message=result["message"]
            )
        elif result["status"] == "already_disabled":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"],
                    "message": result["message"]
                },
                message="Plugin was already disabled"
            )
        elif result["status"] == "dependency_conflict":
            return create_error_response(
                message=result["message"],
                status_code=424,  # Failed Dependency
                details={
                    "dependent_plugins": result.get("dependent_plugins"),
                    "plugin_name": result["plugin_name"]
                }
            )
        elif result["status"] == "not_found":
            return create_error_response(
                message=result["message"],
                status_code=404,
                details={"plugin_name": result["plugin_name"]}
            )
        else:
            return create_error_response(
                message=result["message"],
                status_code=500,
                details={"result": result}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to disable plugin '{plugin_name}'"
        )


@router.get("/active")
async def list_active_plugins():
    """
    List all currently active plugins.

    Returns:
        JSON response with active plugins list
    """
    try:
        active_plugins = await get_active_plugins()

        return create_success_response(
            data={
                "active_plugins": active_plugins,
                "total_count": len(active_plugins)
            },
            message="Active plugins retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to list active plugins"
        )


@router.post("/batch/activate")
async def batch_activate_plugins(
    plugin_names: List[str],
    parallel: bool = Query(True, description="Activate plugins in parallel")
):
    """
    Activate multiple plugins at once.

    Args:
        plugin_names: List of plugin names to activate
        parallel: Whether to activate plugins in parallel

    Returns:
        JSON response with batch activation results
    """
    try:
        result = await plugin_activation_service.activate_multiple_plugins(
            plugin_names, parallel
        )

        return create_success_response(
            data={
                "total_requested": result["total_requested"],
                "successful": result["successful"],
                "failed": result["failed"],
                "skipped": result["skipped"],
                "detailed_results": result["results"]
            },
            message=f"Batch activation completed: {result['successful']} succeeded, {result['failed']} failed"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to batch activate plugins"
        )


@router.post("/batch/deactivate")
async def batch_deactivate_plugins(
    plugin_names: List[str],
    parallel: bool = Query(True, description="Deactivate plugins in parallel")
):
    """
    Deactivate multiple plugins at once.

    Args:
        plugin_names: List of plugin names to deactivate
        parallel: Whether to deactivate plugins in parallel

    Returns:
        JSON response with batch deactivation results
    """
    try:
        result = await plugin_activation_service.deactivate_multiple_plugins(
            plugin_names, parallel
        )

        return create_success_response(
            data={
                "total_requested": result["total_requested"],
                "successful": result["successful"],
                "failed": result["failed"],
                "skipped": result["skipped"],
                "detailed_results": result["results"]
            },
            message=f"Batch deactivation completed: {result['successful']} succeeded, {result['failed']} failed"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to batch deactivate plugins"
        )


@router.get("/{plugin_name}/dependencies")
async def get_plugin_dependencies(plugin_name: str):
    """
    Get dependencies for a specific plugin.

    Args:
        plugin_name: Name of the plugin to get dependencies for

    Returns:
        JSON response with plugin dependencies
    """
    try:
        # First check if plugin exists
        plugin_info = await get_plugin_info(plugin_name)
        if not plugin_info:
            return create_error_response(
                message=f"Plugin '{plugin_name}' not found",
                status_code=404
            )

        dependencies = await plugin_activation_service.get_activation_requirements(plugin_name)

        return create_success_response(
            data=dependencies,
            message=f"Dependencies for plugin '{plugin_name}' retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to get dependencies for plugin '{plugin_name}'"
        )


@router.post("/reload-all")
async def reload_all_plugins():
    """
    Reload all plugins in the system.

    Returns:
        JSON response with reload results
    """
    try:
        # Unload all currently loaded plugins
        active_plugins = await get_active_plugins()
        plugin_names = [p["name"] for p in active_plugins]

        # Deactivate all active plugins first
        deactivate_result = await plugin_activation_service.deactivate_multiple_plugins(
            plugin_names, parallel=True
        )

        # Refresh the registry
        refresh_result = await plugin_registry_service.refresh_registry()

        # Reload all registered plugins
        registered_plugins = await get_registered_plugins()
        registered_plugin_names = [p["name"] for p in registered_plugins if p["enabled"]]

        activate_result = await plugin_activation_service.activate_multiple_plugins(
            registered_plugin_names, parallel=True
        )

        return create_success_response(
            data={
                "deactivation_result": deactivate_result,
                "refresh_result": refresh_result,
                "activation_result": activate_result,
                "reloaded_at": datetime.utcnow().isoformat()
            },
            message="All plugins reloaded successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to reload all plugins"
        )


@router.delete("/{plugin_name}")
async def unregister_plugin_endpoint(plugin_name: str):
    """
    Unregister a plugin from the system.

    Args:
        plugin_name: Name of the plugin to unregister

    Returns:
        JSON response with unregistration result
    """
    try:
        # First deactivate if active
        if await is_plugin_active(plugin_name):
            deactivate_result = await deactivate_plugin(plugin_name)
            if deactivate_result["status"] not in ["deactivated", "already_inactive"]:
                return create_error_response(
                    message=f"Could not deactivate plugin before unregistering: {deactivate_result['message']}",
                    status_code=500
                )

        # Now unregister the plugin
        result = await plugin_registry_service.unregister_plugin(plugin_name)

        if result["status"] == "success":
            return create_success_response(
                data={
                    "plugin_name": result["plugin_name"]
                },
                message=result["message"]
            )
        elif result["status"] == "dependency_conflict":
            return create_error_response(
                message=result["message"],
                status_code=424,  # Failed Dependency
                details={
                    "dependent_plugins": result.get("dependent_plugins"),
                    "plugin_name": result["plugin_name"]
                }
            )
        elif result["status"] == "not_found":
            return create_error_response(
                message=result["message"],
                status_code=404,
                details={"plugin_name": result["plugin_name"]}
            )
        else:
            return create_error_response(
                message=result["message"],
                status_code=500,
                details={"result": result}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message=f"Failed to unregister plugin '{plugin_name}'"
        )


# Register the router in the main app
def register_plugin_routes(app):
    """
    Register plugin routes with the main application.

    Args:
        app: The FastAPI application instance
    """
    app.include_router(router)