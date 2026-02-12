"""
Tool permissions checking service for the x-agent2 AI assistant system.

This module handles permission validation for tool execution based on user roles,
tool categories, and system policies.
"""

from typing import Dict, List, Optional, Any, Union
from enum import Enum
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
import json
from pathlib import Path

from src.agent_core.config.config_service import get_config


class PermissionAction(Enum):
    """Actions that require permission checks."""
    EXECUTE_TOOL = "execute_tool"
    VIEW_TOOL = "view_tool"
    CONFIGURE_TOOL = "configure_tool"
    MANAGE_TOOL = "manage_tool"


class PermissionLevel(Enum):
    """Levels of permission required."""
    NONE = "none"
    READ = "read"
    EXECUTE = "execute"
    MODIFY = "modify"
    ADMIN = "admin"


class ToolCategory(Enum):
    """Categories of tools for permission grouping."""
    SYSTEM = "system"
    SECURITY = "security"
    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    WEB = "web"
    CODE = "code"
    DATABASE = "database"
    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    CUSTOM = "custom"


@dataclass
class UserPermissions:
    """User permissions structure."""
    user_id: str
    roles: List[str]
    allowed_tools: List[str]
    restricted_tools: List[str]
    permissions: Dict[str, PermissionLevel]
    effective_date: datetime
    expiration_date: Optional[datetime]


@dataclass
class ToolPermission:
    """Individual tool permission configuration."""
    tool_name: str
    required_permission: PermissionLevel
    allowed_categories: List[ToolCategory]
    allowed_roles: List[str]
    restrictions: Dict[str, Any]
    metadata: Dict[str, Any]


class PermissionChecker:
    """Core permission checking logic."""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Default permission mappings
        self.default_permissions = {
            # High-risk tools requiring admin permissions
            "command_exec": PermissionLevel.ADMIN,
            "system_info": PermissionLevel.ADMIN,
            "network_scan": PermissionLevel.ADMIN,
            "port_scan": PermissionLevel.ADMIN,

            # Medium-risk tools requiring execute permissions
            "file_system": PermissionLevel.EXECUTE,
            "database_access": PermissionLevel.EXECUTE,

            # Lower-risk tools requiring read permissions
            "web_search": PermissionLevel.READ,
            "web_scrape": PermissionLevel.READ,
            "calculator": PermissionLevel.READ,

            # General productivity tools
            "email": PermissionLevel.READ,
            "calendar": PermissionLevel.READ,
        }

        # Role-based permissions
        self.role_permissions = {
            "admin": [PermissionLevel.NONE, PermissionLevel.READ, PermissionLevel.EXECUTE, PermissionLevel.MODIFY, PermissionLevel.ADMIN],
            "power_user": [PermissionLevel.NONE, PermissionLevel.READ, PermissionLevel.EXECUTE, PermissionLevel.MODIFY],
            "user": [PermissionLevel.NONE, PermissionLevel.READ, PermissionLevel.EXECUTE],
            "guest": [PermissionLevel.NONE, PermissionLevel.READ],
        }

        # Tool category mappings
        self.tool_category_mapping = {
            "command_exec": ToolCategory.SYSTEM,
            "system_info": ToolCategory.SYSTEM,
            "network_scan": ToolCategory.NETWORK,
            "port_scan": ToolCategory.NETWORK,
            "file_system": ToolCategory.FILE_SYSTEM,
            "database_access": ToolCategory.DATABASE,
            "web_search": ToolCategory.WEB,
            "web_scrape": ToolCategory.WEB,
            "calculator": ToolCategory.PRODUCTIVITY,
            "email": ToolCategory.COMMUNICATION,
            "calendar": ToolCategory.PRODUCTIVITY,
        }

        # Load additional permissions from config if available
        self._load_permissions_from_config()

    def _load_permissions_from_config(self):
        """Load permissions from configuration."""
        # This would load from a permissions config file in a real implementation
        # For now, we'll use the default permissions defined above
        pass

    def check_permission(
        self,
        user_perms: UserPermissions,
        tool_name: str,
        action: PermissionAction = PermissionAction.EXECUTE_TOOL
    ) -> Dict[str, Any]:
        """
        Check if a user has permission to perform an action on a tool.

        Args:
            user_perms: User's permissions
            tool_name: Name of the tool
            action: Action to check permissions for

        Returns:
            Dictionary with permission check results
        """
        # Check if tool is explicitly restricted
        if tool_name in user_perms.restricted_tools:
            return {
                "allowed": False,
                "reason": f"Tool {tool_name} is explicitly restricted for user {user_perms.user_id}",
                "required_permission": self._get_required_permission(tool_name),
                "user_permission": None
            }

        # Check if tool is explicitly allowed
        if tool_name in user_perms.allowed_tools:
            return {
                "allowed": True,
                "reason": f"Tool {tool_name} is explicitly allowed for user {user_perms.user_id}",
                "required_permission": self._get_required_permission(tool_name),
                "user_permission": self._get_user_permission_level(user_perms, tool_name)
            }

        # Check permission level requirements
        required_perm = self._get_required_permission(tool_name)
        user_perm = self._get_user_permission_level(user_perms, tool_name)

        # Determine if user has sufficient permission
        allowed = self._has_sufficient_permission(required_perm, user_perm)

        return {
            "allowed": allowed,
            "reason": f"Permission check for {tool_name} by user {user_perms.user_id}",
            "required_permission": required_perm,
            "user_permission": user_perm,
            "tool_category": self._get_tool_category(tool_name),
            "user_roles": user_perms.roles
        }

    def _get_required_permission(self, tool_name: str) -> PermissionLevel:
        """Get the required permission level for a tool."""
        return self.default_permissions.get(tool_name, PermissionLevel.READ)

    def _get_user_permission_level(self, user_perms: UserPermissions, tool_name: str) -> Optional[PermissionLevel]:
        """Get the user's permission level for a specific tool."""
        # Check if user has specific permission for this tool
        if tool_name in user_perms.permissions:
            return user_perms.permissions[tool_name]

        # Check by category
        category = self._get_tool_category(tool_name)
        category_perm_key = f"category_{category.value}"
        if category_perm_key in user_perms.permissions:
            return user_perms.permissions[category_perm_key]

        # Check if user has any role that grants this permission
        for role in user_perms.roles:
            if role in self.role_permissions:
                role_perms = self.role_permissions[role]
                required_perm = self._get_required_permission(tool_name)

                # Check if the role permits this level of access
                if required_perm in role_perms:
                    # Find the highest permission the user has for this role
                    available_perms = [perm for perm in role_perms if perm in user_perms.permissions.values()]
                    if available_perms:
                        return max(available_perms, key=lambda p: list(PermissionLevel).index(p))

        return PermissionLevel.NONE

    def _has_sufficient_permission(self, required: PermissionLevel, user_has: Optional[PermissionLevel]) -> bool:
        """Check if user has sufficient permission level."""
        if user_has is None:
            return False

        # Define permission hierarchy
        perm_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.EXECUTE: 2,
            PermissionLevel.MODIFY: 3,
            PermissionLevel.ADMIN: 4
        }

        return perm_hierarchy[user_has] >= perm_hierarchy[required]

    def _get_tool_category(self, tool_name: str) -> ToolCategory:
        """Get the category for a tool."""
        return self.tool_category_mapping.get(tool_name, ToolCategory.CUSTOM)

    def get_user_accessible_tools(self, user_perms: UserPermissions) -> List[str]:
        """
        Get list of tools accessible to a user.

        Args:
            user_perms: User's permissions

        Returns:
            List of accessible tool names
        """
        accessible_tools = []

        # For simplicity, we'll check against a predefined list of tools
        # In a real implementation, this would come from the tool registry
        all_known_tools = list(self.default_permissions.keys())

        for tool_name in all_known_tools:
            perm_check = self.check_permission(user_perms, tool_name)
            if perm_check["allowed"]:
                accessible_tools.append(tool_name)

        # Add any explicitly allowed tools
        for tool_name in user_perms.allowed_tools:
            if tool_name not in accessible_tools:
                accessible_tools.append(tool_name)

        # Remove any explicitly restricted tools
        accessible_tools = [t for t in accessible_tools if t not in user_perms.restricted_tools]

        return accessible_tools

    def validate_tool_parameters(
        self,
        user_perms: UserPermissions,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate that the parameters for a tool are allowed given the user's permissions.

        Args:
            user_perms: User's permissions
            tool_name: Name of the tool
            parameters: Parameters to validate

        Returns:
            Dictionary with validation results
        """
        perm_check = self.check_permission(user_perms, tool_name)

        if not perm_check["allowed"]:
            return {
                "valid": False,
                "errors": [f"User does not have permission to use tool: {tool_name}"],
                "restricted_params": [],
                "warnings": []
            }

        errors = []
        warnings = []
        restricted_params = []

        # Based on the tool category, apply specific restrictions
        category = perm_check["tool_category"]

        if category == ToolCategory.SYSTEM:
            # Restrict potentially dangerous system parameters
            restricted_system_params = ["command", "shell", "execute", "run", "script"]
            for param_name in parameters:
                if any(restricted in param_name.lower() for restricted in restricted_system_params):
                    errors.append(f"Parameter '{param_name}' is restricted for system tools")
                    restricted_params.append(param_name)

        elif category == ToolCategory.FILE_SYSTEM:
            # Restrict file system access parameters
            if "path" in parameters:
                path = str(parameters["path"])
                # Check for potentially dangerous paths
                if ".." in path or path.startswith("/") or path.startswith("~"):
                    warnings.append(f"Path parameter '{path}' may be unsafe")

        elif category == ToolCategory.NETWORK:
            # Restrict network parameters
            if "host" in parameters:
                host = str(parameters["host"])
                # In a real implementation, validate against allowed hosts
                if host in ["localhost", "127.0.0.1", "::1"]:
                    warnings.append(f"Access to localhost may be restricted in some contexts")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "restricted_params": restricted_params,
            "warnings": warnings
        }


class PermissionService:
    """Service class for managing tool permissions."""

    def __init__(self):
        self.permission_checker = PermissionChecker()
        self.logger = logging.getLogger(__name__)

        # In-memory user permissions store (would use database in production)
        self.user_permissions: Dict[str, UserPermissions] = {}

    def set_user_permissions(self, user_perms: UserPermissions):
        """
        Set permissions for a user.

        Args:
            user_perms: User permissions to set
        """
        self.user_permissions[user_perms.user_id] = user_perms

    def get_user_permissions(self, user_id: str) -> Optional[UserPermissions]:
        """
        Get permissions for a user.

        Args:
            user_id: ID of the user

        Returns:
            User permissions if found, None otherwise
        """
        return self.user_permissions.get(user_id)

    def check_tool_permission(
        self,
        user_id: str,
        tool_name: str,
        action: PermissionAction = PermissionAction.EXECUTE_TOOL
    ) -> Dict[str, Any]:
        """
        Check if a user has permission to perform an action on a tool.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool
            action: Action to check permissions for

        Returns:
            Dictionary with permission check results
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return {
                "allowed": False,
                "reason": f"No permissions found for user {user_id}",
                "required_permission": self.permission_checker._get_required_permission(tool_name),
                "user_permission": None
            }

        return self.permission_checker.check_permission(user_perms, tool_name, action)

    def check_tool_parameters(
        self,
        user_id: str,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate tool parameters for a user.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool
            parameters: Parameters to validate

        Returns:
            Dictionary with validation results
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return {
                "valid": False,
                "errors": [f"No permissions found for user {user_id}"],
                "restricted_params": [],
                "warnings": []
            }

        return self.permission_checker.validate_tool_parameters(user_perms, tool_name, parameters)

    def get_accessible_tools(self, user_id: str) -> List[str]:
        """
        Get list of tools accessible to a user.

        Args:
            user_id: ID of the user

        Returns:
            List of accessible tool names
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return []

        return self.permission_checker.get_user_accessible_tools(user_perms)

    def grant_role_to_user(self, user_id: str, role: str) -> bool:
        """
        Grant a role to a user.

        Args:
            user_id: ID of the user
            role: Role to grant

        Returns:
            True if successful, False otherwise
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            # Create default permissions for user
            user_perms = UserPermissions(
                user_id=user_id,
                roles=[],
                allowed_tools=[],
                restricted_tools=[],
                permissions={},
                effective_date=datetime.utcnow(),
                expiration_date=None
            )

        if role not in user_perms.roles:
            user_perms.roles.append(role)
            self.set_user_permissions(user_perms)
            return True

        return False

    def revoke_role_from_user(self, user_id: str, role: str) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: ID of the user
            role: Role to revoke

        Returns:
            True if successful, False otherwise
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return False

        if role in user_perms.roles:
            user_perms.roles.remove(role)
            self.set_user_permissions(user_perms)
            return True

        return False

    def grant_tool_permission(
        self,
        user_id: str,
        tool_name: str,
        permission_level: PermissionLevel
    ) -> bool:
        """
        Grant specific permission for a tool to a user.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool
            permission_level: Permission level to grant

        Returns:
            True if successful, False otherwise
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            # Create default permissions for user
            user_perms = UserPermissions(
                user_id=user_id,
                roles=[],
                allowed_tools=[],
                restricted_tools=[],
                permissions={},
                effective_date=datetime.utcnow(),
                expiration_date=None
            )

        user_perms.permissions[tool_name] = permission_level
        self.set_user_permissions(user_perms)
        return True

    def restrict_tool_for_user(self, user_id: str, tool_name: str) -> bool:
        """
        Restrict a specific tool for a user.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool to restrict

        Returns:
            True if successful, False otherwise
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            # Create default permissions for user
            user_perms = UserPermissions(
                user_id=user_id,
                roles=[],
                allowed_tools=[],
                restricted_tools=[],
                permissions={},
                effective_date=datetime.utcnow(),
                expiration_date=None
            )

        if tool_name not in user_perms.restricted_tools:
            user_perms.restricted_tools.append(tool_name)
            # Remove from allowed tools if it was there
            if tool_name in user_perms.allowed_tools:
                user_perms.allowed_tools.remove(tool_name)

            self.set_user_permissions(user_perms)
            return True

        return False

    def allow_tool_for_user(self, user_id: str, tool_name: str) -> bool:
        """
        Allow a specific tool for a user.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool to allow

        Returns:
            True if successful, False otherwise
        """
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            # Create default permissions for user
            user_perms = UserPermissions(
                user_id=user_id,
                roles=[],
                allowed_tools=[],
                restricted_tools=[],
                permissions={},
                effective_date=datetime.utcnow(),
                expiration_date=None
            )

        if tool_name not in user_perms.allowed_tools:
            user_perms.allowed_tools.append(tool_name)
            # Remove from restricted if it was there
            if tool_name in user_perms.restricted_tools:
                user_perms.restricted_tools.remove(tool_name)

            self.set_user_permissions(user_perms)
            return True

        return False

    def create_default_permissions_for_user(self, user_id: str) -> UserPermissions:
        """
        Create default permissions for a new user.

        Args:
            user_id: ID of the user

        Returns:
            Default user permissions
        """
        default_perms = UserPermissions(
            user_id=user_id,
            roles=["user"],  # Default role
            allowed_tools=[],  # No explicitly allowed tools by default
            restricted_tools=[],  # No explicitly restricted tools by default
            permissions={},  # No specific permissions set
            effective_date=datetime.utcnow(),
            expiration_date=None
        )

        self.set_user_permissions(default_perms)
        return default_perms

    def refresh_permissions_cache(self):
        """
        Refresh the permissions cache.
        In a real implementation, this might reload permissions from database.
        """
        # In this in-memory implementation, there's no cache to refresh
        # In a database-backed implementation, this would reload from DB
        pass


class RoleManager:
    """Manages user roles and role-based permissions."""

    def __init__(self, permission_service: PermissionService):
        self.permission_service = permission_service
        self.logger = logging.getLogger(__name__)

        # Define system roles
        self.system_roles = {
            "admin": {
                "description": "Administrator with full system access",
                "permissions": ["admin", "modify", "execute", "read"]
            },
            "power_user": {
                "description": "Power user with extended tool access",
                "permissions": ["modify", "execute", "read"]
            },
            "user": {
                "description": "Standard user with basic tool access",
                "permissions": ["execute", "read"]
            },
            "guest": {
                "description": "Guest user with limited access",
                "permissions": ["read"]
            }
        }

    def create_role(self, role_name: str, description: str, permissions: List[str]) -> bool:
        """
        Create a new role.

        Args:
            role_name: Name of the role
            description: Description of the role
            permissions: List of permissions for the role

        Returns:
            True if successful, False otherwise
        """
        if role_name in self.system_roles:
            self.logger.warning(f"Role {role_name} already exists")
            return False

        self.system_roles[role_name] = {
            "description": description,
            "permissions": permissions
        }

        return True

    def assign_role_to_user(self, user_id: str, role_name: str) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: ID of the user
            role_name: Name of the role to assign

        Returns:
            True if successful, False otherwise
        """
        if role_name not in self.system_roles:
            self.logger.error(f"Role {role_name} does not exist")
            return False

        return self.permission_service.grant_role_to_user(user_id, role_name)

    def remove_role_from_user(self, user_id: str, role_name: str) -> bool:
        """
        Remove a role from a user.

        Args:
            user_id: ID of the user
            role_name: Name of the role to remove

        Returns:
            True if successful, False otherwise
        """
        if role_name not in self.system_roles:
            self.logger.error(f"Role {role_name} does not exist")
            return False

        return self.permission_service.revoke_role_from_user(user_id, role_name)

    def get_user_effective_permissions(self, user_id: str) -> Dict[str, Any]:
        """
        Get effective permissions for a user based on their roles.

        Args:
            user_id: ID of the user

        Returns:
            Dictionary with effective permissions
        """
        user_perms = self.permission_service.get_user_permissions(user_id)
        if not user_perms:
            return {"roles": [], "effective_permissions": [], "accessible_tools": []}

        # Determine effective permissions from roles
        effective_perms = set()
        for role in user_perms.roles:
            if role in self.permission_service.role_permissions:
                effective_perms.update(self.permission_service.role_permissions[role])

        # Add any explicitly granted permissions
        for perm_level in user_perms.permissions.values():
            effective_perms.add(perm_level)

        return {
            "user_id": user_id,
            "roles": user_perms.roles,
            "effective_permissions": [perm.value for perm in effective_perms],
            "accessible_tools": self.permission_service.get_accessible_tools(user_id)
        }


# Global instances
permission_service = PermissionService()
role_manager = RoleManager(permission_service)


# Convenience functions
def check_tool_permission(
    user_id: str,
    tool_name: str,
    action: PermissionAction = PermissionAction.EXECUTE_TOOL
) -> Dict[str, Any]:
    """Check if a user has permission to use a tool."""
    return permission_service.check_tool_permission(user_id, tool_name, action)


def check_tool_parameters(
    user_id: str,
    tool_name: str,
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate tool parameters for a user."""
    return permission_service.check_tool_parameters(user_id, tool_name, parameters)


def get_accessible_tools(user_id: str) -> List[str]:
    """Get list of tools accessible to a user."""
    return permission_service.get_accessible_tools(user_id)


def grant_role_to_user(user_id: str, role: str) -> bool:
    """Grant a role to a user."""
    return permission_service.grant_role_to_user(user_id, role)


def revoke_role_from_user(user_id: str, role: str) -> bool:
    """Revoke a role from a user."""
    return permission_service.revoke_role_from_user(user_id, role)


def grant_tool_permission(
    user_id: str,
    tool_name: str,
    permission_level: PermissionLevel
) -> bool:
    """Grant specific permission for a tool to a user."""
    return permission_service.grant_tool_permission(user_id, tool_name, permission_level)