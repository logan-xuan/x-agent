"""
Plugin manifest parser for the x-agent2 AI assistant system.

This module handles parsing and validating plugin manifest files (plugin.json)
that define plugin metadata, dependencies, and configuration.
"""

import json
import yaml
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import re
from enum import Enum


class PluginType(Enum):
    """Types of plugins supported by the system."""
    SKILL = "skill"
    INTEGRATION = "integration"
    TOOL = "tool"
    ENHANCEMENT = "enhancement"
    EXTENSION = "extension"


class CompatibilityLevel(Enum):
    """Compatibility levels for plugins."""
    FULL = "full"
    PARTIAL = "partial"
    EXPERIMENTAL = "experimental"
    INCOMPATIBLE = "incompatible"


@dataclass
class PluginManifestSchema:
    """Defines the schema for a plugin manifest."""
    name: str
    version: str
    description: str
    author: str
    license: str
    repository: str
    main_module: str
    entry_point: str
    dependencies: List[str]
    min_xagent_version: str
    permissions: List[str]
    enabled: bool
    config_schema: Dict[str, Any]
    tags: List[str]
    plugin_type: PluginType
    compatibility_level: CompatibilityLevel
    install_requires: List[str]
    extras_require: Dict[str, List[str]]
    xagent_api_version: str
    icon: Optional[str] = None
    homepage: Optional[str] = None
    documentation: Optional[str] = None


class ManifestValidationError(Exception):
    """Exception raised when a manifest fails validation."""
    pass


class PluginManifestParser:
    """Parses and validates plugin manifest files."""

    def __init__(self):
        # Define the required fields for a valid manifest
        self.required_fields = {
            "name", "version", "description", "author", "main_module", "entry_point"
        }

        # Define the expected field types
        self.field_types = {
            "name": str,
            "version": str,
            "description": str,
            "author": str,
            "license": str,
            "repository": str,
            "main_module": str,
            "entry_point": str,
            "dependencies": list,
            "min_xagent_version": str,
            "permissions": list,
            "enabled": bool,
            "config_schema": dict,
            "tags": list,
            "plugin_type": str,
            "compatibility_level": str,
            "install_requires": list,
            "extras_require": dict,
            "xagent_api_version": str,
            "icon": str,
            "homepage": str,
            "documentation": str
        }

    def parse_manifest(self, manifest_path: Union[str, Path]) -> PluginManifestSchema:
        """
        Parse a plugin manifest file and return a PluginManifestSchema object.

        Args:
            manifest_path: Path to the manifest file (JSON or YAML)

        Returns:
            PluginManifestSchema object representing the parsed manifest

        Raises:
            ManifestValidationError: If the manifest is invalid
        """
        manifest_path = Path(manifest_path)

        if not manifest_path.exists():
            raise ManifestValidationError(f"Manifest file does not exist: {manifest_path}")

        # Determine file format and parse accordingly
        if manifest_path.suffix.lower() in ['.json']:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        elif manifest_path.suffix.lower() in ['.yaml', '.yml']:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        else:
            raise ManifestValidationError(f"Unsupported manifest file format: {manifest_path.suffix}")

        # Validate the manifest data
        self.validate_manifest(data, str(manifest_path))

        # Create and return the manifest schema object
        return PluginManifestSchema(
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            license=data.get("license", "MIT"),
            repository=data.get("repository", ""),
            main_module=data["main_module"],
            entry_point=data["entry_point"],
            dependencies=data.get("dependencies", []),
            min_xagent_version=data.get("min_xagent_version", "1.0.0"),
            permissions=data.get("permissions", []),
            enabled=data.get("enabled", True),
            config_schema=data.get("config_schema", {}),
            tags=data.get("tags", []),
            plugin_type=PluginType(data.get("plugin_type", "extension")),
            compatibility_level=CompatibilityLevel(data.get("compatibility_level", "full")),
            install_requires=data.get("install_requires", []),
            extras_require=data.get("extras_require", {}),
            xagent_api_version=data.get("xagent_api_version", "1.0"),
            icon=data.get("icon"),
            homepage=data.get("homepage"),
            documentation=data.get("documentation")
        )

    def validate_manifest(self, data: Dict[str, Any], manifest_path: str = "") -> Dict[str, Any]:
        """
        Validate a manifest dictionary against the required schema.

        Args:
            data: Dictionary containing manifest data
            manifest_path: Optional path for error reporting

        Returns:
            Dictionary with validation results

        Raises:
            ManifestValidationError: If validation fails
        """
        errors = []
        warnings = []

        # Check required fields
        missing_fields = self.required_fields - set(data.keys())
        if missing_fields:
            errors.append(f"Missing required fields: {', '.join(missing_fields)}")

        # Validate field types
        for field, value in data.items():
            if field in self.field_types:
                expected_type = self.field_types[field]

                # Special handling for optional fields
                if value is None and field in ["icon", "homepage", "documentation"]:
                    continue

                # Handle union types (str or list)
                if expected_type == list and not isinstance(value, list):
                    if not isinstance(value, (list, type(None))):
                        errors.append(f"Field '{field}' must be a list, got {type(value).__name__}")
                elif expected_type == dict and not isinstance(value, dict):
                    errors.append(f"Field '{field}' must be a dict, got {type(value).__name__}")
                elif expected_type == str and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be a string, got {type(value).__name__}")
                elif expected_type == bool and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be a boolean, got {type(value).__name__}")

        # Validate specific field formats
        if "name" in data:
            name = data["name"]
            if not re.match(r'^[a-zA-Z0-9_-]+$', name):
                errors.append(f"Plugin name '{name}' contains invalid characters. Only alphanumeric, hyphens, and underscores are allowed.")

        if "version" in data:
            version = data["version"]
            # Basic semver validation (X.Y.Z format)
            if not re.match(r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9-.]+)?(?:\+[a-zA-Z0-9-.]+)?$', version):
                warnings.append(f"Version '{version}' doesn't follow standard semver format (X.Y.Z)")

        if "repository" in data and data["repository"]:
            repo_url = data["repository"]
            if not re.match(r'^https?://', repo_url):
                warnings.append(f"Repository URL should be a valid HTTP(S) URL: {repo_url}")

        if "homepage" in data and data["homepage"]:
            homepage_url = data["homepage"]
            if not re.match(r'^https?://', homepage_url):
                warnings.append(f"Homepage URL should be a valid HTTP(S) URL: {homepage_url}")

        if "documentation" in data and data["documentation"]:
            docs_url = data["documentation"]
            if not re.match(r'^https?://', docs_url):
                warnings.append(f"Documentation URL should be a valid HTTP(S) URL: {docs_url}")

        # Validate dependencies format
        if "dependencies" in data:
            for dep in data["dependencies"]:
                if not isinstance(dep, str):
                    errors.append(f"All dependencies must be strings, got {type(dep).__name__} for '{dep}'")

        # Validate permissions format
        if "permissions" in data:
            for perm in data["permissions"]:
                if not isinstance(perm, str):
                    errors.append(f"All permissions must be strings, got {type(perm).__name__} for '{perm}'")

        # Validate plugin type
        if "plugin_type" in data:
            try:
                PluginType(data["plugin_type"])
            except ValueError:
                errors.append(f"Invalid plugin type: {data['plugin_type']}. Valid types are: {[pt.value for pt in PluginType]}")

        # Validate compatibility level
        if "compatibility_level" in data:
            try:
                CompatibilityLevel(data["compatibility_level"])
            except ValueError:
                errors.append(f"Invalid compatibility level: {data['compatibility_level']}. Valid levels are: {[cl.value for cl in CompatibilityLevel]}")

        # Check for deprecated fields
        deprecated_fields = {
            "api_version": "Use 'xagent_api_version' instead",
            "minimum_version": "Use 'min_xagent_version' instead"
        }

        for field, replacement in deprecated_fields.items():
            if field in data:
                warnings.append(f"Deprecated field '{field}' found. {replacement}")

        if errors:
            error_msg = f"Manifest validation failed for {manifest_path}: {'; '.join(errors)}"
            raise ManifestValidationError(error_msg)

        return {
            "is_valid": True,
            "warnings": warnings,
            "errors": []
        }

    def validate_plugin_compatibility(
        self,
        manifest: PluginManifestSchema,
        system_version: str
    ) -> Dict[str, Any]:
        """
        Validate if a plugin is compatible with the current system version.

        Args:
            manifest: Plugin manifest to validate
            system_version: Current system version

        Returns:
            Dictionary with compatibility information
        """
        # Parse version strings for comparison
        def parse_version(version_str):
            parts = version_str.split('.')
            return tuple(int(part.split('-')[0]) for part in parts)  # Ignore pre-release parts for comparison

        try:
            min_required = parse_version(manifest.min_xagent_version)
            current = parse_version(system_version)

            is_compatible = current >= min_required

            return {
                "is_compatible": is_compatible,
                "min_required_version": manifest.min_xagent_version,
                "current_version": system_version,
                "compatibility_level": manifest.compatibility_level.value,
                "message": "Plugin is compatible" if is_compatible else f"Plugin requires at least version {manifest.min_xagent_version}, current is {system_version}"
            }
        except Exception as e:
            return {
                "is_compatible": False,
                "min_required_version": manifest.min_xagent_version,
                "current_version": system_version,
                "compatibility_level": manifest.compatibility_level.value,
                "error": str(e),
                "message": f"Could not determine compatibility: {str(e)}"
            }

    def normalize_manifest(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a manifest dictionary by filling in defaults and standardizing fields.

        Args:
            data: Raw manifest data

        Returns:
            Normalized manifest data
        """
        normalized = data.copy()

        # Set defaults for optional fields
        defaults = {
            "license": "MIT",
            "repository": "",
            "enabled": True,
            "dependencies": [],
            "permissions": [],
            "config_schema": {},
            "tags": [],
            "plugin_type": "extension",
            "compatibility_level": "full",
            "install_requires": [],
            "extras_require": {},
            "xagent_api_version": "1.0"
        }

        for field, default_value in defaults.items():
            if field not in normalized:
                normalized[field] = default_value

        # Normalize the plugin type and compatibility level to enum values
        if "plugin_type" in normalized:
            try:
                normalized["plugin_type"] = PluginType(normalized["plugin_type"]).value
            except ValueError:
                normalized["plugin_type"] = "extension"  # fallback to default

        if "compatibility_level" in normalized:
            try:
                normalized["compatibility_level"] = CompatibilityLevel(normalized["compatibility_level"]).value
            except ValueError:
                normalized["compatibility_level"] = "full"  # fallback to default

        return normalized

    def create_template_manifest(self, plugin_name: str) -> Dict[str, Any]:
        """
        Create a template manifest for a new plugin.

        Args:
            plugin_name: Name of the new plugin

        Returns:
            Template manifest dictionary
        """
        return {
            "name": plugin_name,
            "version": "1.0.0",
            "description": f"A new plugin for x-agent2: {plugin_name}",
            "author": "Plugin Developer",
            "license": "MIT",
            "repository": "",
            "main_module": f"{plugin_name}.py",
            "entry_point": "PluginClass",
            "dependencies": [],
            "min_xagent_version": "1.0.0",
            "permissions": [],
            "enabled": True,
            "config_schema": {},
            "tags": ["custom"],
            "plugin_type": "extension",
            "compatibility_level": "full",
            "install_requires": [],
            "extras_require": {},
            "xagent_api_version": "1.0",
            "icon": None,
            "homepage": None,
            "documentation": None
        }


class PluginManifestManager:
    """High-level manager for handling plugin manifests."""

    def __init__(self):
        self.parser = PluginManifestParser()

    def load_and_validate_manifest(
        self,
        manifest_path: Union[str, Path],
        system_version: str
    ) -> Dict[str, Any]:
        """
        Load a manifest file and validate it against system requirements.

        Args:
            manifest_path: Path to the manifest file
            system_version: Current system version for compatibility check

        Returns:
            Dictionary with manifest data and validation results
        """
        try:
            # Parse the manifest
            manifest = self.parser.parse_manifest(manifest_path)

            # Validate compatibility
            compat_result = self.parser.validate_plugin_compatibility(manifest, system_version)

            # Normalize the manifest data
            normalized_data = self.parser.normalize_manifest(manifest.__dict__)

            return {
                "manifest": normalized_data,
                "is_valid": True,
                "is_compatible": compat_result["is_compatible"],
                "compatibility_info": compat_result,
                "validation_warnings": []
            }
        except ManifestValidationError as e:
            return {
                "error": str(e),
                "is_valid": False,
                "is_compatible": False,
                "compatibility_info": {},
                "validation_warnings": []
            }
        except Exception as e:
            return {
                "error": f"Unexpected error parsing manifest: {str(e)}",
                "is_valid": False,
                "is_compatible": False,
                "compatibility_info": {},
                "validation_warnings": []
            }

    def create_manifest_file(
        self,
        plugin_name: str,
        output_path: Union[str, Path],
        template_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a new manifest file for a plugin.

        Args:
            plugin_name: Name of the plugin
            output_path: Path where the manifest should be saved
            template_data: Optional custom template data

        Returns:
            True if successful, False otherwise
        """
        try:
            output_path = Path(output_path)

            # Create template data if not provided
            if template_data is None:
                template_data = self.parser.create_template_manifest(plugin_name)

            # Write the manifest to file (JSON format)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error creating manifest file: {e}")
            return False


# Global instance
manifest_parser = PluginManifestParser()
manifest_manager = PluginManifestManager()


# Convenience functions
def parse_manifest(manifest_path: Union[str, Path]) -> Optional[PluginManifestSchema]:
    """Parse a plugin manifest file."""
    try:
        return manifest_parser.parse_manifest(manifest_path)
    except ManifestValidationError as e:
        print(f"Error parsing manifest: {e}")
        return None


def validate_manifest(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a manifest dictionary."""
    return manifest_parser.validate_manifest(data)


def validate_plugin_compatibility(
    manifest: PluginManifestSchema,
    system_version: str
) -> Dict[str, Any]:
    """Validate plugin compatibility with system version."""
    return manifest_parser.validate_plugin_compatibility(manifest, system_version)