"""
Plugin configuration service for the x-agent2 AI assistant system.

This module handles the configuration management for plugins, including
loading, validating, and applying configuration settings.
"""

import json
import yaml
from typing import Dict, Any, Optional, Union, List
from datetime import datetime
import os
from pathlib import Path
import logging
from enum import Enum


class ConfigScope(Enum):
    """Scope levels for configuration settings."""
    GLOBAL = "global"
    USER = "user"
    SESSION = "session"
    PLUGIN = "plugin"


class ConfigValueType(Enum):
    """Types of configuration values."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    OBJECT = "object"
    SECRET = "secret"


class PluginConfigManager:
    """Manages configuration for plugins."""

    def __init__(self, config_dir: Optional[str] = None):
        self.logger = logging.getLogger(__name__)

        # Set up config directory
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path("config")

        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Store configurations in memory
        self._configurations: Dict[str, Dict[str, Any]] = {}
        self._defaults: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

        # Configuration file paths
        self.global_config_path = self.config_dir / "plugins.json"
        self.schema_path = self.config_dir / "plugin-schemas.json"

    def load_global_config(self) -> Dict[str, Any]:
        """
        Load the global plugin configuration from file.

        Returns:
            Dictionary with global plugin configuration
        """
        if self.global_config_path.exists():
            try:
                with open(self.global_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                self._configurations['__global__'] = config
                self.logger.info(f"Loaded global plugin configuration from {self.global_config_path}")
                return config
            except Exception as e:
                self.logger.error(f"Failed to load global config from {self.global_config_path}: {e}")
                return {}
        else:
            # Create default config file
            default_config = {
                "plugins": {},
                "settings": {
                    "auto_reload": True,
                    "sandbox_mode": "limited",
                    "enable_monitoring": True
                }
            }

            self.save_global_config(default_config)
            self._configurations['__global__'] = default_config
            return default_config

    def save_global_config(self, config: Dict[str, Any]):
        """
        Save the global plugin configuration to file.

        Args:
            config: Global configuration to save
        """
        try:
            with open(self.global_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self._configurations['__global__'] = config
            self.logger.info(f"Saved global plugin configuration to {self.global_config_path}")
        except Exception as e:
            self.logger.error(f"Failed to save global config to {self.global_config_path}: {e}")

    def load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        Load configuration for a specific plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dictionary with plugin configuration
        """
        config_path = self.config_dir / f"plugin-{plugin_name}.json"

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                self._configurations[plugin_name] = config
                self.logger.info(f"Loaded configuration for plugin {plugin_name} from {config_path}")
                return config
            except Exception as e:
                self.logger.error(f"Failed to load config for plugin {plugin_name} from {config_path}: {e}")
                return {}
        else:
            # Get default configuration for the plugin
            default_config = self.get_plugin_defaults(plugin_name)
            self._configurations[plugin_name] = default_config

            # Create the config file with defaults
            self.save_plugin_config(plugin_name, default_config)
            return default_config

    def save_plugin_config(self, plugin_name: str, config: Dict[str, Any]):
        """
        Save configuration for a specific plugin.

        Args:
            plugin_name: Name of the plugin
            config: Configuration to save
        """
        config_path = self.config_dir / f"plugin-{plugin_name}.json"

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self._configurations[plugin_name] = config
            self.logger.info(f"Saved configuration for plugin {plugin_name} to {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to save config for plugin {plugin_name} to {config_path}: {e}")

    def get_plugin_defaults(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get default configuration for a plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dictionary with default configuration
        """
        if plugin_name in self._defaults:
            return self._defaults[plugin_name]

        # Default configuration for any plugin
        default_config = {
            "enabled": True,
            "auto_start": False,
            "resource_limits": {
                "max_memory_mb": 256,
                "timeout_seconds": 30,
                "max_concurrent": 5
            },
            "permissions": {
                "allow_network": False,
                "allow_filesystem": False,
                "allow_system_commands": False
            },
            "logging": {
                "level": "INFO",
                "enabled": True
            }
        }

        self._defaults[plugin_name] = default_config
        return default_config

    def set_plugin_defaults(self, plugin_name: str, defaults: Dict[str, Any]):
        """
        Set default configuration for a plugin.

        Args:
            plugin_name: Name of the plugin
            defaults: Default configuration values
        """
        self._defaults[plugin_name] = defaults

    def get_config_value(
        self,
        plugin_name: str,
        key: str,
        default: Optional[Any] = None,
        scope: ConfigScope = ConfigScope.PLUGIN
    ) -> Any:
        """
        Get a configuration value for a plugin.

        Args:
            plugin_name: Name of the plugin
            key: Configuration key
            default: Default value if key not found
            scope: Configuration scope

        Returns:
            Configuration value
        """
        if scope == ConfigScope.PLUGIN:
            config = self.get_plugin_config(plugin_name)
            return self._get_nested_value(config, key, default)
        elif scope == ConfigScope.GLOBAL:
            config = self.get_global_config()
            return self._get_nested_value(config.get('plugins', {}).get(plugin_name, {}), key, default)
        else:
            # For USER or SESSION scopes, we'd need additional logic
            # For now, just use PLUGIN scope as default
            config = self.get_plugin_config(plugin_name)
            return self._get_nested_value(config, key, default)

    def set_config_value(
        self,
        plugin_name: str,
        key: str,
        value: Any,
        scope: ConfigScope = ConfigScope.PLUGIN
    ):
        """
        Set a configuration value for a plugin.

        Args:
            plugin_name: Name of the plugin
            key: Configuration key
            value: Value to set
            scope: Configuration scope
        """
        if scope == ConfigScope.PLUGIN:
            config = self.get_plugin_config(plugin_name)
            self._set_nested_value(config, key, value)
            self.save_plugin_config(plugin_name, config)
        elif scope == ConfigScope.GLOBAL:
            config = self.get_global_config()
            plugin_config = config.get('plugins', {}).get(plugin_name, {})
            self._set_nested_value(plugin_config, key, value)
            config.setdefault('plugins', {})[plugin_name] = plugin_config
            self.save_global_config(config)

    def _get_nested_value(self, obj: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        Get a nested value using dot notation (e.g., 'resource_limits.max_memory_mb').

        Args:
            obj: Object to get value from
            key: Dot-notation key
            default: Default value if key not found

        Returns:
            Value at the key or default
        """
        keys = key.split('.')
        current = obj

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        return current

    def _set_nested_value(self, obj: Dict[str, Any], key: str, value: Any):
        """
        Set a nested value using dot notation.

        Args:
            obj: Object to set value in
            key: Dot-notation key
            value: Value to set
        """
        keys = key.split('.')
        current = obj

        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get the configuration for a specific plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Plugin configuration
        """
        if plugin_name in self._configurations:
            return self._configurations[plugin_name]

        return self.load_plugin_config(plugin_name)

    def get_global_config(self) -> Dict[str, Any]:
        """
        Get the global plugin configuration.

        Returns:
            Global configuration
        """
        if '__global__' in self._configurations:
            return self._configurations['__global__']

        return self.load_global_config()

    def validate_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate plugin configuration against its schema.

        Args:
            plugin_name: Name of the plugin
            config: Configuration to validate

        Returns:
            Dictionary with validation results
        """
        schema = self.get_plugin_schema(plugin_name)

        if not schema:
            return {
                "valid": True,
                "errors": [],
                "warnings": ["No schema found for plugin, validation skipped"]
            }

        return self._validate_against_schema(config, schema)

    def _validate_against_schema(self, config: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration against a schema.

        Args:
            config: Configuration to validate
            schema: Schema to validate against

        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []

        def validate_recursive(conf, sch, path=""):
            if not isinstance(conf, dict) or not isinstance(sch, dict):
                return

            # Check required fields
            required = sch.get("required", [])
            for req_field in required:
                if req_field not in conf:
                    errors.append(f"Missing required field: {path}{req_field}")

            # Validate each field in config
            for field, value in conf.items():
                field_path = f"{path}{field}."

                if field in sch.get("properties", {}):
                    field_schema = sch["properties"][field]

                    # Validate type
                    expected_type = field_schema.get("type")
                    if expected_type:
                        if expected_type == "string" and not isinstance(value, str):
                            errors.append(f"Field {path}{field} should be a string, got {type(value).__name__}")
                        elif expected_type == "integer" and not isinstance(value, int):
                            errors.append(f"Field {path}{field} should be an integer, got {type(value).__name__}")
                        elif expected_type == "number" and not isinstance(value, (int, float)):
                            errors.append(f"Field {path}{field} should be a number, got {type(value).__name__}")
                        elif expected_type == "boolean" and not isinstance(value, bool):
                            errors.append(f"Field {path}{field} should be a boolean, got {type(value).__name__}")
                        elif expected_type == "array" and not isinstance(value, list):
                            errors.append(f"Field {path}{field} should be an array, got {type(value).__name__}")
                        elif expected_type == "object" and not isinstance(value, dict):
                            errors.append(f"Field {path}{field} should be an object, got {type(value).__name__}")

                    # Validate enum values
                    if "enum" in field_schema and value not in field_schema["enum"]:
                        errors.append(f"Field {path}{field} value {value} is not in allowed values: {field_schema['enum']}")

                    # Recursively validate nested objects
                    if isinstance(value, dict) and "properties" in field_schema:
                        validate_recursive(value, field_schema, field_path)

        validate_recursive(config, schema)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def get_plugin_schema(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the schema for a plugin's configuration.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Configuration schema if found, None otherwise
        """
        if plugin_name in self._schemas:
            return self._schemas[plugin_name]

        # Try to load from file
        schema_path = self.config_dir / f"schema-{plugin_name}.json"
        if schema_path.exists():
            try:
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                self._schemas[plugin_name] = schema
                return schema
            except Exception as e:
                self.logger.error(f"Failed to load schema for plugin {plugin_name}: {e}")
                return None

        return None

    def save_plugin_schema(self, plugin_name: str, schema: Dict[str, Any]):
        """
        Save the schema for a plugin's configuration.

        Args:
            plugin_name: Name of the plugin
            schema: Configuration schema
        """
        schema_path = self.config_dir / f"schema-{plugin_name}.json"

        try:
            with open(schema_path, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2, ensure_ascii=False)

            self._schemas[plugin_name] = schema
            self.logger.info(f"Saved schema for plugin {plugin_name} to {schema_path}")
        except Exception as e:
            self.logger.error(f"Failed to save schema for plugin {plugin_name}: {e}")

    def reset_plugin_config(self, plugin_name: str):
        """
        Reset a plugin's configuration to defaults.

        Args:
            plugin_name: Name of the plugin
        """
        default_config = self.get_plugin_defaults(plugin_name)
        self.save_plugin_config(plugin_name, default_config)
        self._configurations[plugin_name] = default_config

    def reset_all_configs(self):
        """Reset all plugin configurations to defaults."""
        for plugin_name in list(self._configurations.keys()):
            if plugin_name != '__global__':
                self.reset_plugin_config(plugin_name)

    def get_all_plugin_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get configurations for all plugins.

        Returns:
            Dictionary mapping plugin names to their configurations
        """
        configs = {}

        # Look for all plugin config files
        for config_file in self.config_dir.glob("plugin-*.json"):
            plugin_name = config_file.name[len("plugin-"):-len(".json")]
            configs[plugin_name] = self.get_plugin_config(plugin_name)

        return configs

    def export_config(self, plugin_name: str, output_path: str, format: str = "json"):
        """
        Export plugin configuration to a file.

        Args:
            plugin_name: Name of the plugin
            output_path: Path to export to
            format: Export format ("json" or "yaml")
        """
        config = self.get_plugin_config(plugin_name)

        output_path = Path(output_path)

        try:
            if format.lower() == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
            elif format.lower() == "yaml":
                with open(output_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported format: {format}")

            self.logger.info(f"Exported config for plugin {plugin_name} to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to export config for plugin {plugin_name}: {e}")

    def import_config(self, plugin_name: str, input_path: str, format: str = "json"):
        """
        Import plugin configuration from a file.

        Args:
            plugin_name: Name of the plugin
            input_path: Path to import from
            format: Import format ("json" or "yaml")
        """
        input_path = Path(input_path)

        try:
            if format.lower() == "json":
                with open(input_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            elif format.lower() == "yaml":
                with open(input_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported format: {format}")

            # Validate the config
            validation_result = self.validate_plugin_config(plugin_name, config)

            if validation_result["valid"]:
                self.save_plugin_config(plugin_name, config)
                self.logger.info(f"Imported config for plugin {plugin_name} from {input_path}")
            else:
                self.logger.error(f"Validation failed when importing config for plugin {plugin_name}: {validation_result['errors']}")

        except Exception as e:
            self.logger.error(f"Failed to import config for plugin {plugin_name} from {input_path}: {e}")


class DynamicConfigManager:
    """Manages runtime configuration changes."""

    def __init__(self, plugin_config_manager: PluginConfigManager):
        self.config_manager = plugin_config_manager
        self.logger = logging.getLogger(__name__)
        self._observers: Dict[str, List[callable]] = {}  # plugin_name -> list of callbacks

    def register_config_observer(self, plugin_name: str, callback: callable):
        """
        Register a callback to be notified when a plugin's config changes.

        Args:
            plugin_name: Name of the plugin
            callback: Function to call when config changes
        """
        if plugin_name not in self._observers:
            self._observers[plugin_name] = []

        self._observers[plugin_name].append(callback)

    def unregister_config_observer(self, plugin_name: str, callback: callable):
        """
        Unregister a config observer callback.

        Args:
            plugin_name: Name of the plugin
            callback: Function to unregister
        """
        if plugin_name in self._observers:
            if callback in self._observers[plugin_name]:
                self._observers[plugin_name].remove(callback)

    def notify_config_change(self, plugin_name: str, old_config: Dict[str, Any], new_config: Dict[str, Any]):
        """
        Notify observers of a configuration change.

        Args:
            plugin_name: Name of the plugin
            old_config: Previous configuration
            new_config: New configuration
        """
        if plugin_name in self._observers:
            for callback in self._observers[plugin_name]:
                try:
                    callback(plugin_name, old_config, new_config)
                except Exception as e:
                    self.logger.error(f"Error in config observer callback for {plugin_name}: {e}")

    def update_config_with_notification(
        self,
        plugin_name: str,
        key: str,
        value: Any,
        scope: ConfigScope = ConfigScope.PLUGIN
    ):
        """
        Update a configuration value and notify observers.

        Args:
            plugin_name: Name of the plugin
            key: Configuration key
            value: New value
            scope: Configuration scope
        """
        old_config = self.config_manager.get_plugin_config(plugin_name).copy()

        self.config_manager.set_config_value(plugin_name, key, value, scope)

        new_config = self.config_manager.get_plugin_config(plugin_name)
        self.notify_config_change(plugin_name, old_config, new_config)

    def bulk_update_config(
        self,
        plugin_name: str,
        updates: Dict[str, Any],
        scope: ConfigScope = ConfigScope.PLUGIN
    ):
        """
        Update multiple configuration values and notify observers once.

        Args:
            plugin_name: Name of the plugin
            updates: Dictionary of key-value pairs to update
            scope: Configuration scope
        """
        old_config = self.config_manager.get_plugin_config(plugin_name).copy()

        for key, value in updates.items():
            self.config_manager.set_config_value(plugin_name, key, value, scope)

        new_config = self.config_manager.get_plugin_config(plugin_name)
        self.notify_config_change(plugin_name, old_config, new_config)


class SecureConfigManager:
    """Handles secure configuration management with encryption for sensitive data."""

    def __init__(self, plugin_config_manager: PluginConfigManager, encryption_key: Optional[str] = None):
        self.config_manager = plugin_config_manager
        self.logger = logging.getLogger(__name__)

        # For a real implementation, we would use a proper encryption library like cryptography
        # For this implementation, we'll just use a simple XOR cipher for demonstration
        self.encryption_key = encryption_key or os.environ.get("CONFIG_ENCRYPTION_KEY", "default-key-change-in-production")

    def encrypt_value(self, value: str) -> str:
        """
        Encrypt a configuration value.

        Args:
            value: Value to encrypt

        Returns:
            Encrypted value
        """
        # Simple XOR encryption for demonstration
        # In production, use a strong encryption algorithm
        encrypted_chars = []
        for i, char in enumerate(value):
            key_char = self.encryption_key[i % len(self.encryption_key)]
            encrypted_char = chr(ord(char) ^ ord(key_char))
            encrypted_chars.append(encrypted_char)

        return ''.join(encrypted_chars)

    def decrypt_value(self, encrypted_value: str) -> str:
        """
        Decrypt a configuration value.

        Args:
            encrypted_value: Value to decrypt

        Returns:
            Decrypted value
        """
        # Decrypt using the same XOR approach
        decrypted_chars = []
        for i, char in enumerate(encrypted_value):
            key_char = self.encryption_key[i % len(self.encryption_key)]
            decrypted_char = chr(ord(char) ^ ord(key_char))
            decrypted_chars.append(decrypted_char)

        return ''.join(decrypted_chars)

    def save_secure_config(self, plugin_name: str, config: Dict[str, Any]):
        """
        Save configuration with encryption for sensitive values.

        Args:
            plugin_name: Name of the plugin
            config: Configuration to save
        """
        # Deep copy the config to avoid modifying the original
        import copy
        config_copy = copy.deepcopy(config)

        # Encrypt sensitive values (those that might be secrets)
        def encrypt_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if self._is_sensitive_key(key):
                        if isinstance(value, str):
                            obj[key] = self.encrypt_value(value)
                    elif isinstance(value, (dict, list)):
                        encrypt_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        encrypt_recursive(item)

        encrypt_recursive(config_copy)
        self.config_manager.save_plugin_config(plugin_name, config_copy)

    def load_secure_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        Load configuration with decryption for sensitive values.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Configuration with decrypted sensitive values
        """
        config = self.config_manager.get_plugin_config(plugin_name)

        # Deep copy to avoid modifying the stored config
        import copy
        config_copy = copy.deepcopy(config)

        # Decrypt sensitive values
        def decrypt_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if self._is_sensitive_key(key):
                        if isinstance(value, str):
                            try:
                                obj[key] = self.decrypt_value(value)
                            except:
                                # If decryption fails, leave as-is
                                pass
                    elif isinstance(value, (dict, list)):
                        decrypt_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        decrypt_recursive(item)

        decrypt_recursive(config_copy)
        return config_copy

    def _is_sensitive_key(self, key: str) -> bool:
        """
        Determine if a configuration key holds sensitive information.

        Args:
            key: Configuration key name

        Returns:
            True if the key is for sensitive data, False otherwise
        """
        sensitive_indicators = [
            'password', 'secret', 'token', 'key', 'credential', 'auth',
            'api_key', 'client_secret', 'private', 'certificate'
        ]

        key_lower = key.lower()
        return any(indicator in key_lower for indicator in sensitive_indicators)


# Global instances
plugin_config_manager = PluginConfigManager()
dynamic_config_manager = DynamicConfigManager(plugin_config_manager)
secure_config_manager = SecureConfigManager(plugin_config_manager)


# Convenience functions
def load_plugin_config(plugin_name: str) -> Dict[str, Any]:
    """Load configuration for a plugin."""
    return plugin_config_manager.load_plugin_config(plugin_name)


def save_plugin_config(plugin_name: str, config: Dict[str, Any]):
    """Save configuration for a plugin."""
    plugin_config_manager.save_plugin_config(plugin_name, config)


def get_config_value(plugin_name: str, key: str, default: Optional[Any] = None) -> Any:
    """Get a configuration value for a plugin."""
    return plugin_config_manager.get_config_value(plugin_name, key, default)


def set_config_value(plugin_name: str, key: str, value: Any):
    """Set a configuration value for a plugin."""
    plugin_config_manager.set_config_value(plugin_name, key, value)


def validate_plugin_config(plugin_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate plugin configuration against its schema."""
    return plugin_config_manager.validate_plugin_config(plugin_name, config)


def reset_plugin_config(plugin_name: str):
    """Reset a plugin's configuration to defaults."""
    plugin_config_manager.reset_plugin_config(plugin_name)


def register_config_observer(plugin_name: str, callback: callable):
    """Register a callback to be notified when a plugin's config changes."""
    dynamic_config_manager.register_config_observer(plugin_name, callback)


def update_config_with_notification(plugin_name: str, key: str, value: Any):
    """Update a configuration value and notify observers."""
    dynamic_config_manager.update_config_with_notification(plugin_name, key, value)


def encrypt_value(value: str) -> str:
    """Encrypt a configuration value."""
    return secure_config_manager.encrypt_value(value)


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a configuration value."""
    return secure_config_manager.decrypt_value(encrypted_value)