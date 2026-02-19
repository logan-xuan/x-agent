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


class WorkspaceConfig(BaseModel):
    """Workspace configuration."""
    
    path: str = Field(default="workspace", description="Path to workspace directory")
    skills_dir: str = Field(
        default="skills",
        description="User skills directory (relative to workspace path)"
    )


class SearchConfig(BaseModel):
    """Hybrid search configuration.
    
    Controls the behavior of memory search combining vector and text similarity.
    """
    
    vector_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for vector similarity score (0.0-1.0)"
    )
    text_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for text similarity score (0.0-1.0)"
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold for search results"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of search results to return"
    )
    
    @model_validator(mode="after")
    def validate_weights(self) -> "SearchConfig":
        """Ensure weights sum to approximately 1.0."""
        total = self.vector_weight + self.text_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"vector_weight + text_weight must equal 1.0, got {total}")
        return self


class CompressionConfig(BaseModel):
    """Context compression configuration.
    
    Controls when and how conversation context is compressed to manage token usage.
    """
    
    threshold_rounds: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Trigger compression when message count exceeds this threshold"
    )
    threshold_tokens: int = Field(
        default=4000,
        ge=1000,
        le=32000,
        description="Trigger compression when token count exceeds this threshold"
    )
    retention_count: int = Field(
        default=50,
        ge=5,
        le=200,
        description="Number of most recent messages to retain after compression"
    )


class PlanConfig(BaseModel):
    """Plan mode configuration.
    
    Controls the behavior of task planning and replanning for complex tasks.
    """
    
    consecutive_failures: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Trigger replanning after this many consecutive failures"
    )
    stuck_iterations: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Trigger replanning if stuck on same step for this many iterations without progress"
    )
    max_replan_count: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum number of replanning attempts before giving up (prevents infinite loops)"
    )


class SkillMetadata(BaseModel):
    """Single skill metadata entry."""
    
    name: str = Field(..., description="Skill name (directory name)")
    description: str = Field(..., description="Skill description")
    keywords: list[str] = Field(default_factory=list, description="Keywords for skill matching")
    auto_trigger: bool = Field(default=True, description="Whether to auto-trigger this skill")
    priority: int = Field(default=999, ge=1, le=999, description="Priority (lower number = higher priority)")


class SkillsConfig(BaseModel):
    """Skills metadata configuration.
    
    Controls skill discovery and recommendation in task analysis phase.
    """
    
    registered: list[SkillMetadata] = Field(
        default_factory=list,
        description="List of registered skills with metadata"
    )
    
    def get_skill_by_name(self, name: str) -> SkillMetadata | None:
        """Get skill metadata by name."""
        for skill in self.registered:
            if skill.name == name:
                return skill
        return None
    
    def get_auto_trigger_skills(self) -> list[SkillMetadata]:
        """Get skills that can be auto-triggered."""
        return [s for s in self.registered if s.auto_trigger]
    
    def match_skills_by_keywords(self, query: str) -> list[SkillMetadata]:
        """Match skills based on query keywords."""
        matched = []
        query_lower = query.lower()
        
        for skill in self.registered:
            # Check if any keyword matches
            for keyword in skill.keywords:
                if keyword.lower() in query_lower:
                    matched.append(skill)
                    break
        
        # Sort by priority
        return sorted(matched, key=lambda s: s.priority)


class ToolsConfig(BaseModel):
    """Tools configuration.
    
    Controls the behavior and security settings for agent tools.
    """
    
    # Terminal tool configuration
    terminal_blacklist: list[str] = Field(
        default_factory=lambda: [
            "rm",
            "dd",
            "mkfs",
            "fdisk",
            "format",
            "shutdown",
            "reboot",
            "poweroff",
            "halt",
            "init",
            "systemctl",
            "service",
            "sudo",
            "su",
            "passwd",
            "chpasswd",
        ],
        description="List of blocked commands for terminal tool"
    )
    terminal_timeout: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Default timeout for terminal commands in seconds"
    )
    terminal_max_output: int = Field(
        default=10000,
        ge=1000,
        le=100000,
        description="Maximum output length before truncation"
    )
    terminal_allowed_dirs: list[str] = Field(
        default_factory=list,
        description="List of allowed working directories (empty = any directory)"
    )
    terminal_high_risk: list[str] = Field(
        default_factory=lambda: [
            "kill",
            "pkill",
            "killall",
            "docker",
            "kubectl",
            "helm",
            "terraform",
            "ansible-playbook",
            "pip",
            "npm",
            "yarn",
            "pnpm",
            "apt",
            "apt-get",
            "yum",
            "dnf",
            "pacman",
            "brew",
        ],
        description="List of high-risk commands requiring user confirmation"
    )


class Config(BaseModel):
    """Root configuration model."""
    
    models: list[ModelConfig] = Field(..., min_length=1, description="Model configurations")
    server: ServerConfig = Field(default_factory=ServerConfig, description="Server config")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging config")
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig, description="Workspace config")
    search: SearchConfig = Field(default_factory=SearchConfig, description="Hybrid search config")
    tools: ToolsConfig = Field(default_factory=ToolsConfig, description="Tools config")
    compression: CompressionConfig = Field(default_factory=CompressionConfig, description="Context compression config")
    plan: PlanConfig = Field(default_factory=PlanConfig, description="Plan mode config")
    skills: SkillsConfig = Field(default_factory=SkillsConfig, description="Skills metadata config")
    
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
