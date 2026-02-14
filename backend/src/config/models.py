"""Pydantic models for configuration."""

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator, model_validator


class ModelConfig(BaseModel):
    """Model configuration - vendor-agnostic design.
    
    Supports any OpenAI-compatible API provider.
    """
    
    name: str = Field(..., description="Configuration name (e.g., primary, backup-1)")
    provider: Literal["openai", "bailian", "custom"] = Field(
        ..., description="Provider type"
    )
    base_url: HttpUrl = Field(..., description="API base URL")
    api_key: SecretStr = Field(..., description="API key (encrypted in memory)")
    model_id: str = Field(..., description="Model identifier")
    is_primary: bool = Field(default=False, description="Whether this is the primary model")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Request timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=5, description="Max retry attempts")
    priority: int = Field(default=0, ge=0, description="Backup priority (lower = higher priority)")
    
    def get_masked_key(self) -> str:
        """Return masked API key for logging."""
        key = self.api_key.get_secret_value()
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


class ServerConfig(BaseModel):
    """Server configuration."""
    
    host: str = Field(default="0.0.0.0", description="Listen address")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description="Allowed CORS origins"
    )
    reload: bool = Field(default=False, description="Enable auto-reload (dev mode)")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Log level"
    )
    format: Literal["json", "text"] = Field(default="json", description="Log format")
    file: str = Field(default="logs/x-agent.log", description="Log file path")
    max_size: str = Field(default="10MB", description="Max log file size")
    backup_count: int = Field(default=5, ge=0, description="Number of backup files")
    console: bool = Field(default=True, description="Output to console")


class Config(BaseModel):
    """Root configuration model."""
    
    models: list[ModelConfig] = Field(..., min_length=1, description="Model configurations")
    server: ServerConfig = Field(default_factory=ServerConfig, description="Server config")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging config")
    
    @field_validator("models")
    @classmethod
    def validate_primary_model(cls, v: list[ModelConfig]) -> list[ModelConfig]:
        """Ensure exactly one primary model exists."""
        primaries = [m for m in v if m.is_primary]
        if len(primaries) != 1:
            raise ValueError(f"Must have exactly one primary model, found {len(primaries)}")
        return v
    
    @model_validator(mode="after")
    def validate_backup_priorities(self) -> "Config":
        """Validate backup model priorities."""
        backups = [m for m in self.models if not m.is_primary]
        if backups:
            priorities = [b.priority for b in backups]
            if len(priorities) != len(set(priorities)):
                raise ValueError("Backup model priorities must be unique")
        return self
    
    def get_primary_model(self) -> ModelConfig:
        """Get the primary model configuration."""
        for model in self.models:
            if model.is_primary:
                return model
        raise RuntimeError("No primary model found")
    
    def get_backup_models(self) -> list[ModelConfig]:
        """Get backup models sorted by priority."""
        backups = [m for m in self.models if not m.is_primary]
        return sorted(backups, key=lambda m: m.priority)
    
    def get_model_by_name(self, name: str) -> ModelConfig | None:
        """Get model configuration by name."""
        for model in self.models:
            if model.name == name:
                return model
        return None
