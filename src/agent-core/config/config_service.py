"""
Configuration management system for the x-agent2 AI assistant system.

This module handles loading, validating, and managing application configuration
settings across different environments.
"""

import os
import json
from typing import Any, Dict, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import yaml
from enum import Enum


class Environment(Enum):
    """Application environments."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    host: str = "localhost"
    port: int = 5432
    username: str = "postgres"
    password: str = ""
    database: str = "xagent2"
    pool_size: int = 10
    echo_sql: bool = False

    def get_database_url(self) -> str:
        """Get the database URL for SQLAlchemy."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class LLMProviderConfig:
    """LLM provider configuration settings."""
    provider: str = "openai"  # openai, anthropic, azure, etc.
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout: int = 30


@dataclass
class SecurityConfig:
    """Security-related configuration settings."""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60 * 24  # 24 hours
    csrf_enabled: bool = True
    cors_origins: list = field(default_factory=lambda: ["*"])
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds


@dataclass
class FileStorageConfig:
    """File storage configuration settings."""
    upload_directory: str = "workspace/user-files"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    allowed_extensions: list = field(default_factory=lambda: [
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".txt", ".csv", ".pdf", ".json",
        ".doc", ".docx", ".xls", ".xlsx",
        ".zip", ".rar", ".tar", ".gz"
    ])
    storage_type: str = "local"  # local, s3, gcs, etc.


@dataclass
class MonitoringConfig:
    """Monitoring and logging configuration settings."""
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    metrics_enabled: bool = True
    trace_logging: bool = False
    performance_monitoring: bool = True


@dataclass
class AppConfig:
    """Main application configuration."""
    app_name: str = "x-agent2"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm_provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    file_storage: FileStorageConfig = field(default_factory=FileStorageConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    version: str = "1.0.0"
    maintenance_mode: bool = False


class ConfigLoader:
    """Loads configuration from various sources."""

    def __init__(self):
        self.config_paths = [
            "config/app.yaml",
            "config/app.yml",
            "config/app.json",
            "config/settings.yaml",
            "config/settings.yml",
            "config/settings.json",
            ".env"
        ]

    def load_from_yaml(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def load_from_json(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}

        # Database config
        db_host = os.getenv('DB_HOST')
        if db_host:
            config['database'] = {
                'host': db_host,
                'port': int(os.getenv('DB_PORT', 5432)),
                'username': os.getenv('DB_USERNAME', 'postgres'),
                'password': os.getenv('DB_PASSWORD', ''),
                'database': os.getenv('DB_NAME', 'xagent2'),
                'pool_size': int(os.getenv('DB_POOL_SIZE', 10)),
                'echo_sql': os.getenv('DB_ECHO_SQL', '').lower() == 'true'
            }

        # LLM Provider config
        llm_provider = os.getenv('LLM_PROVIDER')
        if llm_provider:
            config['llm_provider'] = {
                'provider': llm_provider,
                'api_key': os.getenv('LLM_API_KEY', ''),
                'model': os.getenv('LLM_MODEL', 'gpt-3.5-turbo'),
                'temperature': float(os.getenv('LLM_TEMPERATURE', '0.7')),
                'max_tokens': int(os.getenv('LLM_MAX_TOKENS', '1000')),
                'timeout': int(os.getenv('LLM_TIMEOUT', '30'))
            }

        # Security config
        jwt_secret = os.getenv('JWT_SECRET')
        if jwt_secret:
            config['security'] = {
                'jwt_secret': jwt_secret,
                'jwt_algorithm': os.getenv('JWT_ALGORITHM', 'HS256'),
                'jwt_expiration_minutes': int(os.getenv('JWT_EXPIRATION_MINUTES', '1440')),
                'csrf_enabled': os.getenv('CSRF_ENABLED', 'true').lower() == 'true',
                'cors_origins': os.getenv('CORS_ORIGINS', '*').split(','),
                'rate_limit_requests': int(os.getenv('RATE_LIMIT_REQUESTS', '100')),
                'rate_limit_window': int(os.getenv('RATE_LIMIT_WINDOW', '60'))
            }

        # App config
        config.update({
            'app_name': os.getenv('APP_NAME', 'x-agent2'),
            'environment': os.getenv('ENVIRONMENT', 'development'),
            'debug': os.getenv('DEBUG', 'false').lower() == 'true',
            'host': os.getenv('HOST', '0.0.0.0'),
            'port': int(os.getenv('PORT', '8000')),
            'version': os.getenv('VERSION', '1.0.0'),
            'maintenance_mode': os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
        })

        return config

    def merge_configs(self, *configs: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge configuration dictionaries."""
        result = {}

        for config in configs:
            for key, value in config.items():
                if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                    # Recursively merge nested dictionaries
                    result[key] = self.merge_configs(result[key], value)
                else:
                    result[key] = value

        return result


class ConfigValidator:
    """Validates configuration settings."""

    @staticmethod
    def validate_database_config(config: DatabaseConfig) -> Dict[str, Any]:
        """Validate database configuration."""
        errors = []

        if not config.host:
            errors.append("Database host is required")
        if config.port <= 0 or config.port > 65535:
            errors.append("Database port must be between 1 and 65535")
        if not config.database:
            errors.append("Database name is required")
        if config.pool_size <= 0:
            errors.append("Database pool size must be positive")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    @staticmethod
    def validate_llm_config(config: LLMProviderConfig) -> Dict[str, Any]:
        """Validate LLM provider configuration."""
        errors = []

        if not config.provider:
            errors.append("LLM provider is required")
        if not config.api_key:
            errors.append("LLM API key is required")
        if not config.model:
            errors.append("LLM model is required")
        if config.temperature < 0 or config.temperature > 2:
            errors.append("LLM temperature must be between 0 and 2")
        if config.max_tokens <= 0:
            errors.append("LLM max tokens must be positive")
        if config.timeout <= 0:
            errors.append("LLM timeout must be positive")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    @staticmethod
    def validate_security_config(config: SecurityConfig) -> Dict[str, Any]:
        """Validate security configuration."""
        errors = []

        if not config.jwt_secret:
            errors.append("JWT secret is required")
        if len(config.jwt_secret) < 16:
            errors.append("JWT secret should be at least 16 characters long")
        if config.jwt_expiration_minutes <= 0:
            errors.append("JWT expiration must be positive")
        if config.rate_limit_requests <= 0:
            errors.append("Rate limit requests must be positive")
        if config.rate_limit_window <= 0:
            errors.append("Rate limit window must be positive")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    @staticmethod
    def validate_app_config(config: AppConfig) -> Dict[str, Any]:
        """Validate the entire application configuration."""
        errors = []
        warnings = []

        # Validate environment
        try:
            Environment(config.environment if isinstance(config.environment, str) else config.environment.value)
        except ValueError:
            errors.append(f"Invalid environment: {config.environment}")

        # Validate port
        if config.port <= 0 or config.port > 65535:
            errors.append("Port must be between 1 and 65535")

        # Validate debug mode in production
        if config.environment == Environment.PRODUCTION and config.debug:
            warnings.append("Debug mode should be disabled in production")

        # Validate individual config sections
        db_validation = ConfigValidator.validate_database_config(config.database)
        if not db_validation["is_valid"]:
            errors.extend([f"Database: {error}" for error in db_validation["errors"]])

        llm_validation = ConfigValidator.validate_llm_config(config.llm_provider)
        if not llm_validation["is_valid"]:
            errors.extend([f"LLM: {error}" for error in llm_validation["errors"]])

        security_validation = ConfigValidator.validate_security_config(config.security)
        if not security_validation["is_valid"]:
            errors.extend([f"Security: {error}" for error in security_validation["errors"]])

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


class ConfigurationManager:
    """Main configuration manager for the application."""

    def __init__(self, config_file: Optional[Union[str, Path]] = None):
        self.config_loader = ConfigLoader()
        self.config_validator = ConfigValidator()
        self.config: AppConfig = self._load_and_validate_config(config_file)

    def _load_and_validate_config(self, config_file: Optional[Union[str, Path]]) -> AppConfig:
        """Load and validate the configuration."""
        # Start with default config
        config_dict = self._get_default_config_dict()

        # Load from file if specified
        if config_file:
            config_file = Path(config_file)
            if config_file.suffix.lower() in ['.yaml', '.yml']:
                file_config = self.config_loader.load_from_yaml(config_file)
            elif config_file.suffix.lower() == '.json':
                file_config = self.config_loader.load_from_json(config_file)
            else:
                raise ValueError(f"Unsupported config file format: {config_file.suffix}")

            config_dict = self.config_loader.merge_configs(config_dict, file_config)

        # Load from environment variables (highest priority)
        env_config = self.config_loader.load_from_env()
        config_dict = self.config_loader.merge_configs(config_dict, env_config)

        # Create config object
        app_config = self._dict_to_config(config_dict)

        # Validate config
        validation_result = self.config_validator.validate_app_config(app_config)
        if not validation_result["is_valid"]:
            raise ValueError(f"Invalid configuration: {'; '.join(validation_result['errors'])}")

        return app_config

    def _get_default_config_dict(self) -> Dict[str, Any]:
        """Get the default configuration as a dictionary."""
        default_config = AppConfig()
        return {
            "app_name": default_config.app_name,
            "environment": default_config.environment.value,
            "debug": default_config.debug,
            "host": default_config.host,
            "port": default_config.port,
            "database": {
                "host": default_config.database.host,
                "port": default_config.database.port,
                "username": default_config.database.username,
                "password": default_config.database.password,
                "database": default_config.database.database,
                "pool_size": default_config.database.pool_size,
                "echo_sql": default_config.database.echo_sql
            },
            "llm_provider": {
                "provider": default_config.llm_provider.provider,
                "api_key": default_config.llm_provider.api_key,
                "model": default_config.llm_provider.model,
                "temperature": default_config.llm_provider.temperature,
                "max_tokens": default_config.llm_provider.max_tokens,
                "timeout": default_config.llm_provider.timeout
            },
            "security": {
                "jwt_secret": default_config.security.jwt_secret,
                "jwt_algorithm": default_config.security.jwt_algorithm,
                "jwt_expiration_minutes": default_config.security.jwt_expiration_minutes,
                "csrf_enabled": default_config.security.csrf_enabled,
                "cors_origins": default_config.security.cors_origins,
                "rate_limit_requests": default_config.security.rate_limit_requests,
                "rate_limit_window": default_config.security.rate_limit_window
            },
            "file_storage": {
                "upload_directory": default_config.file_storage.upload_directory,
                "max_file_size": default_config.file_storage.max_file_size,
                "allowed_extensions": default_config.file_storage.allowed_extensions,
                "storage_type": default_config.file_storage.storage_type
            },
            "monitoring": {
                "log_level": default_config.monitoring.log_level,
                "log_file": default_config.monitoring.log_file,
                "metrics_enabled": default_config.monitoring.metrics_enabled,
                "trace_logging": default_config.monitoring.trace_logging,
                "performance_monitoring": default_config.monitoring.performance_monitoring
            },
            "version": default_config.version,
            "maintenance_mode": default_config.maintenance_mode
        }

    def _dict_to_config(self, config_dict: Dict[str, Any]) -> AppConfig:
        """Convert a dictionary to a configuration object."""
        # Convert environment string to enum
        env_str = config_dict.get('environment', 'development')
        if isinstance(env_str, str):
            environment = Environment(env_str.lower())
        else:
            environment = env_str

        return AppConfig(
            app_name=config_dict.get('app_name', 'x-agent2'),
            environment=environment,
            debug=config_dict.get('debug', False),
            host=config_dict.get('host', '0.0.0.0'),
            port=config_dict.get('port', 8000),
            database=DatabaseConfig(
                host=config_dict.get('database', {}).get('host', 'localhost'),
                port=config_dict.get('database', {}).get('port', 5432),
                username=config_dict.get('database', {}).get('username', 'postgres'),
                password=config_dict.get('database', {}).get('password', ''),
                database=config_dict.get('database', {}).get('database', 'xagent2'),
                pool_size=config_dict.get('database', {}).get('pool_size', 10),
                echo_sql=config_dict.get('database', {}).get('echo_sql', False)
            ),
            llm_provider=LLMProviderConfig(
                provider=config_dict.get('llm_provider', {}).get('provider', 'openai'),
                api_key=config_dict.get('llm_provider', {}).get('api_key', ''),
                model=config_dict.get('llm_provider', {}).get('model', 'gpt-3.5-turbo'),
                temperature=config_dict.get('llm_provider', {}).get('temperature', 0.7),
                max_tokens=config_dict.get('llm_provider', {}).get('max_tokens', 1000),
                timeout=config_dict.get('llm_provider', {}).get('timeout', 30)
            ),
            security=SecurityConfig(
                jwt_secret=config_dict.get('security', {}).get('jwt_secret', ''),
                jwt_algorithm=config_dict.get('security', {}).get('jwt_algorithm', 'HS256'),
                jwt_expiration_minutes=config_dict.get('security', {}).get('jwt_expiration_minutes', 60 * 24),
                csrf_enabled=config_dict.get('security', {}).get('csrf_enabled', True),
                cors_origins=config_dict.get('security', {}).get('cors_origins', ["*"]),
                rate_limit_requests=config_dict.get('security', {}).get('rate_limit_requests', 100),
                rate_limit_window=config_dict.get('security', {}).get('rate_limit_window', 60)
            ),
            file_storage=FileStorageConfig(
                upload_directory=config_dict.get('file_storage', {}).get('upload_directory', 'workspace/user-files'),
                max_file_size=config_dict.get('file_storage', {}).get('max_file_size', 100 * 1024 * 1024),
                allowed_extensions=config_dict.get('file_storage', {}).get('allowed_extensions', [
                    ".jpg", ".jpeg", ".png", ".gif", ".webp",
                    ".txt", ".csv", ".pdf", ".json",
                    ".doc", ".docx", ".xls", ".xlsx",
                    ".zip", ".rar", ".tar", ".gz"
                ]),
                storage_type=config_dict.get('file_storage', {}).get('storage_type', 'local')
            ),
            monitoring=MonitoringConfig(
                log_level=config_dict.get('monitoring', {}).get('log_level', 'INFO'),
                log_file=config_dict.get('monitoring', {}).get('log_file', 'logs/app.log'),
                metrics_enabled=config_dict.get('monitoring', {}).get('metrics_enabled', True),
                trace_logging=config_dict.get('monitoring', {}).get('trace_logging', False),
                performance_monitoring=config_dict.get('monitoring', {}).get('performance_monitoring', True)
            ),
            version=config_dict.get('version', '1.0.0'),
            maintenance_mode=config_dict.get('maintenance_mode', False)
        )

    def reload_config(self, config_file: Optional[Union[str, Path]] = None):
        """Reload the configuration."""
        self.config = self._load_and_validate_config(config_file)

    def get_config(self) -> AppConfig:
        """Get the current configuration."""
        return self.config

    def update_config(self, **kwargs):
        """Update specific configuration values."""
        # This is a simplified implementation
        # In a real application, you might want more sophisticated updating
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def is_production(self) -> bool:
        """Check if the environment is production."""
        return self.config.environment == Environment.PRODUCTION

    def is_debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self.config.debug


# Global configuration instance
config_manager = ConfigurationManager()


# Convenience functions
def get_config() -> AppConfig:
    """Get the global configuration."""
    return config_manager.get_config()


def is_production() -> bool:
    """Check if running in production environment."""
    return config_manager.is_production()


def is_debug() -> bool:
    """Check if debug mode is enabled."""
    return config_manager.is_debug()