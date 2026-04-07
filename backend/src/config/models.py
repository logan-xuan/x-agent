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
    when: str = Field(default="D", description="Time interval for rotation: S=seconds, M=minutes, H=hours, D=days, W=weekday, midnight=end of day")
    interval: int = Field(default=1, ge=1, description="Rotation interval multiplier (e.g., 1 means every day/week)")
    
    # LLM prompt log configuration
    prompt_llm_file: str = Field(default="logs/prompt-llm.log", description="LLM prompt log file path")
    prompt_llm_max_size: str = Field(default="50MB", description="Max LLM prompt log file size")
    prompt_llm_backup_count: int = Field(default=5, ge=0, description="Number of LLM prompt log backups")
    
    # Server log configuration
    server_log_file: str = Field(default="logs/server.log", description="Server log file path")
    server_log_max_size: str = Field(default="10MB", description="Max server log file size")
    server_log_backup_count: int = Field(default=3, ge=0, description="Number of server log backups")
    
    # AgentLogger file persistence configuration
    agent_log_file: str = Field(default="logs/agent-core.log", description="AgentLogger log file path")
    agent_log_max_size: str = Field(default="20MB", description="Max AgentLogger log file size")
    agent_log_backup_count: int = Field(default=5, ge=0, description="Number of AgentLogger log backups")


class WorkspaceConfig(BaseModel):
    """Workspace configuration."""
    
    path: str = Field(default="workspace", description="Path to workspace directory")
    skills_dir: str = Field(
        default="skills",
        description="User skills directory (relative to workspace path)"
    )
    jobs_dir: str = Field(
        default="jobs",
        description="Cron jobs directory (relative to workspace path)"
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
    max_context_tokens: int = Field(default=32000, ge=1000)
    max_tool_message_chars: int = Field(default=4000, ge=100)
    mode: str = Field(default="stateful")
    compression_quality_gate_enabled: bool = Field(default=False)
    min_compression_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    min_token_savings: int = Field(default=0, ge=0)


class RuntimeDefaultsConfig(BaseModel):
    """Default runtime profile selection."""

    turn_profile: str = Field(default="default", description="Default turn budget profile")
    compression_profile: str = Field(
        default="balanced",
        description="Default runtime compression profile",
    )
    session_profile: str = Field(default="default", description="Default session profile")


class RuntimeTurnProfileConfig(BaseModel):
    """Bounded-turn runtime budget profile."""

    max_turns: int = Field(default=12, ge=1, le=100)
    max_wall_time_ms: int = Field(default=180000, ge=1000, le=3600000)
    max_total_tokens: int = Field(default=120000, ge=1000)
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    max_tool_calls: int = Field(default=24, ge=1, le=500)
    max_parallel_tools: int = Field(default=4, ge=1, le=32)
    max_spawns: int = Field(default=3, ge=0, le=32)
    compact_trigger_tokens: int = Field(default=80000, ge=1000)
    collapse_trigger_tokens: int = Field(default=60000, ge=1000)
    tool_result_single_chars: int = Field(default=50000, ge=1000)
    tool_result_per_message_chars: int = Field(default=200000, ge=1000)
    max_tool_calls_by_name: dict[str, int] = Field(default_factory=dict)


class RuntimeCompressionPersistConfig(BaseModel):
    """Persistence thresholds for large runtime tool outputs."""

    single_result_chars: int = Field(default=50000, ge=1000)
    aggregate_result_chars: int = Field(default=200000, ge=1000)
    artifact_preview_chars: int = Field(default=2000, ge=200)
    artifact_preview_head_chars: int = Field(default=900, ge=50)
    artifact_preview_tail_chars: int = Field(default=700, ge=50)


class RuntimeCompressionPressureConfig(BaseModel):
    """Pressure thresholds for staged runtime compaction."""

    yellow_pct: float = Field(default=0.50, gt=0.0, lt=1.0)
    orange_pct: float = Field(default=0.68, gt=0.0, lt=1.0)
    red_pct: float = Field(default=0.82, gt=0.0, lt=1.0)
    hard_stop_pct: float = Field(default=0.90, gt=0.0, lt=1.0)


class RuntimeCompressionPruningConfig(BaseModel):
    """Pruning behavior for old tool outputs."""

    enabled: bool = True
    ttl_ms: int = Field(default=300000, ge=1000)
    preserve_recent_assistants: int = Field(default=3, ge=1, le=20)
    min_prunable_tool_chars: int = Field(default=50000, ge=1000)
    soft_trim_max_chars: int = Field(default=4000, ge=100)
    soft_trim_head_chars: int = Field(default=1500, ge=0)
    soft_trim_tail_chars: int = Field(default=1500, ge=0)
    hard_clear_enabled: bool = True
    hard_clear_placeholder: str = "[Old tool result content cleared]"


class RuntimeCompressionMicrocompactConfig(BaseModel):
    """Targeted trimming before full history collapse."""

    enabled: bool = True
    trigger_pct: float = Field(default=0.50, gt=0.0, lt=1.0)
    max_units_per_pass: int = Field(default=8, ge=1, le=100)
    preserve_error_results: bool = True


class RuntimeCompressionCollapseConfig(BaseModel):
    """Collapse settings for long message histories."""

    enabled: bool = True
    trigger_pct: float = Field(default=0.68, gt=0.0, lt=1.0)
    max_segment_tokens: int = Field(default=12000, ge=100)
    min_segment_turns: int = Field(default=2, ge=1, le=50)


class RuntimeCompressionAutocompactConfig(BaseModel):
    """Autocompact thresholds for runtime history pressure."""

    enabled: bool = True
    trigger_pct: float = Field(default=0.82, gt=0.0, lt=1.0)
    reserve_tokens_floor: int = Field(default=20000, ge=0)
    max_history_share: float = Field(default=0.50, gt=0.0, lt=1.0)
    fallback_summary_max_chars: int = Field(default=8000, ge=500)


class RuntimeCompressionMemoryFlushConfig(BaseModel):
    """Memory flush behavior before runtime compaction."""

    enabled: bool = True
    soft_threshold_tokens: int = Field(default=4000, ge=0)


class RuntimeCompressionQualityConfig(BaseModel):
    """Quality gates for runtime compression output."""

    min_compression_gain_tokens: int = Field(default=0, ge=0)
    require_post_check: bool = True
    rollback_on_invariant_failure: bool = True


class RuntimeCompressionProfileConfig(BaseModel):
    """Named runtime compression profile."""

    mode: str = Field(default="balanced")
    pressure: RuntimeCompressionPressureConfig = Field(default_factory=RuntimeCompressionPressureConfig)
    persist: RuntimeCompressionPersistConfig = Field(default_factory=RuntimeCompressionPersistConfig)
    pruning: RuntimeCompressionPruningConfig = Field(default_factory=RuntimeCompressionPruningConfig)
    microcompact: RuntimeCompressionMicrocompactConfig = Field(
        default_factory=RuntimeCompressionMicrocompactConfig
    )
    collapse: RuntimeCompressionCollapseConfig = Field(default_factory=RuntimeCompressionCollapseConfig)
    autocompact: RuntimeCompressionAutocompactConfig = Field(
        default_factory=RuntimeCompressionAutocompactConfig
    )
    memory_flush: RuntimeCompressionMemoryFlushConfig = Field(
        default_factory=RuntimeCompressionMemoryFlushConfig
    )
    quality: RuntimeCompressionQualityConfig = Field(default_factory=RuntimeCompressionQualityConfig)
    retain_recent_messages: int = Field(default=12, ge=1, le=100)


class RuntimeSessionLaneLimitsConfig(BaseModel):
    """Lane concurrency caps for the session orchestrator."""

    main: int = Field(default=1, ge=1, le=32)
    followup: int = Field(default=2, ge=1, le=32)
    subagent: int = Field(default=4, ge=1, le=64)
    cron: int = Field(default=2, ge=1, le=32)
    background_tool: int = Field(default=2, ge=1, le=32)


class RuntimeSessionProfileConfig(BaseModel):
    """Session lifecycle and child-session defaults."""

    idle_archive_ms: int = Field(default=86400000, ge=60000)
    child_auto_archive_ms: int = Field(default=3600000, ge=60000)
    allow_child_sessions: bool = True
    child_prompt_mode: Literal["full", "minimal", "none"] = Field(default="minimal")
    child_max_depth: int = Field(default=1, ge=0, le=3)
    child_default_budget_profile: str = Field(default="child-default")
    lane_limits: RuntimeSessionLaneLimitsConfig = Field(default_factory=RuntimeSessionLaneLimitsConfig)


class RuntimeToolPolicyConfig(BaseModel):
    """Runtime governance policy for a specific tool."""

    max_result_size_chars: int = Field(default=50000, ge=100)
    max_uses_per_turn: int = Field(default=8, ge=1, le=100)
    max_uses_per_session: int = Field(default=50, ge=1, le=1000)
    max_parallelism: int = Field(default=2, ge=1, le=32)
    default_timeout_ms: int = Field(default=30000, ge=100, le=3600000)
    compactable: bool = True
    persist_large_output: bool = True
    allow_in_subagent: bool = True
    cost_weight: int = Field(default=1, ge=1, le=100)
    repeat_signature_limit: int = Field(default=2, ge=1, le=20)


class RuntimeToolsConfig(BaseModel):
    """Runtime tool policies."""

    defaults: RuntimeToolPolicyConfig = Field(default_factory=RuntimeToolPolicyConfig)
    by_name: dict[str, RuntimeToolPolicyConfig] = Field(default_factory=dict)


def _default_runtime_turn_profiles() -> dict[str, RuntimeTurnProfileConfig]:
    return {
        "default": RuntimeTurnProfileConfig(),
        "delegate-default": RuntimeTurnProfileConfig(
            max_turns=10,
            max_wall_time_ms=240000,
            max_total_tokens=80000,
            max_tool_calls=16,
            max_parallel_tools=4,
            max_spawns=0,
            compact_trigger_tokens=50000,
            collapse_trigger_tokens=38000,
            tool_result_single_chars=40000,
            tool_result_per_message_chars=160000,
        ),
        "child-default": RuntimeTurnProfileConfig(
            max_turns=6,
            max_wall_time_ms=60000,
            max_total_tokens=40000,
            max_tool_calls=8,
            max_parallel_tools=2,
            max_spawns=0,
            compact_trigger_tokens=24000,
            collapse_trigger_tokens=18000,
            tool_result_single_chars=20000,
            tool_result_per_message_chars=80000,
        ),
    }


def _default_runtime_compression_profiles() -> dict[str, RuntimeCompressionProfileConfig]:
    return {
        "balanced": RuntimeCompressionProfileConfig(mode="balanced"),
        "aggressive": RuntimeCompressionProfileConfig(
            mode="aggressive",
            pressure=RuntimeCompressionPressureConfig(
                yellow_pct=0.45,
                orange_pct=0.60,
                red_pct=0.72,
                hard_stop_pct=0.85,
            ),
            persist=RuntimeCompressionPersistConfig(
                single_result_chars=30000,
                aggregate_result_chars=120000,
                artifact_preview_chars=1600,
                artifact_preview_head_chars=700,
                artifact_preview_tail_chars=500,
            ),
            pruning=RuntimeCompressionPruningConfig(
                ttl_ms=180000,
                preserve_recent_assistants=2,
                soft_trim_max_chars=2500,
                soft_trim_head_chars=900,
                soft_trim_tail_chars=900,
            ),
            microcompact=RuntimeCompressionMicrocompactConfig(trigger_pct=0.45, max_units_per_pass=12),
            collapse=RuntimeCompressionCollapseConfig(trigger_pct=0.60, max_segment_tokens=8000),
            autocompact=RuntimeCompressionAutocompactConfig(
                trigger_pct=0.72,
                reserve_tokens_floor=12000,
                max_history_share=0.40,
                fallback_summary_max_chars=5000,
            ),
            memory_flush=RuntimeCompressionMemoryFlushConfig(soft_threshold_tokens=2500),
            quality=RuntimeCompressionQualityConfig(min_compression_gain_tokens=500),
            retain_recent_messages=8,
        ),
        "conservative": RuntimeCompressionProfileConfig(
            mode="conservative",
            pressure=RuntimeCompressionPressureConfig(
                yellow_pct=0.55,
                orange_pct=0.75,
                red_pct=0.88,
                hard_stop_pct=0.94,
            ),
            persist=RuntimeCompressionPersistConfig(
                single_result_chars=80000,
                aggregate_result_chars=260000,
                artifact_preview_chars=2600,
                artifact_preview_head_chars=1100,
                artifact_preview_tail_chars=900,
            ),
            pruning=RuntimeCompressionPruningConfig(
                ttl_ms=600000,
                preserve_recent_assistants=5,
                soft_trim_max_chars=5000,
                soft_trim_head_chars=1800,
                soft_trim_tail_chars=1800,
                hard_clear_enabled=False,
            ),
            microcompact=RuntimeCompressionMicrocompactConfig(trigger_pct=0.60, max_units_per_pass=4),
            collapse=RuntimeCompressionCollapseConfig(trigger_pct=0.75, max_segment_tokens=18000),
            autocompact=RuntimeCompressionAutocompactConfig(
                trigger_pct=0.88,
                reserve_tokens_floor=28000,
                max_history_share=0.60,
                fallback_summary_max_chars=10000,
            ),
            memory_flush=RuntimeCompressionMemoryFlushConfig(soft_threshold_tokens=5000),
            quality=RuntimeCompressionQualityConfig(min_compression_gain_tokens=1500),
            retain_recent_messages=16,
        ),
    }


def _default_runtime_session_profiles() -> dict[str, RuntimeSessionProfileConfig]:
    return {
        "default": RuntimeSessionProfileConfig(),
        "child-default": RuntimeSessionProfileConfig(
            allow_child_sessions=False,
            child_prompt_mode="minimal",
            child_max_depth=0,
        ),
    }


class RuntimeConfig(BaseModel):
    """Top-level runtime configuration tree."""

    defaults: RuntimeDefaultsConfig = Field(default_factory=RuntimeDefaultsConfig)
    turn_profiles: dict[str, RuntimeTurnProfileConfig] = Field(
        default_factory=_default_runtime_turn_profiles
    )
    compression_profiles: dict[str, RuntimeCompressionProfileConfig] = Field(
        default_factory=_default_runtime_compression_profiles
    )
    session_profiles: dict[str, RuntimeSessionProfileConfig] = Field(
        default_factory=_default_runtime_session_profiles
    )
    tools: RuntimeToolsConfig = Field(default_factory=RuntimeToolsConfig)

    @model_validator(mode="after")
    def validate_profile_references(self) -> "RuntimeConfig":
        if self.defaults.turn_profile not in self.turn_profiles:
            raise ValueError(
                f"runtime.defaults.turn_profile references unknown profile '{self.defaults.turn_profile}'"
            )
        if self.defaults.compression_profile not in self.compression_profiles:
            raise ValueError(
                "runtime.defaults.compression_profile references unknown profile "
                f"'{self.defaults.compression_profile}'"
            )
        if self.defaults.session_profile not in self.session_profiles:
            raise ValueError(
                f"runtime.defaults.session_profile references unknown profile '{self.defaults.session_profile}'"
            )

        for name, profile in self.compression_profiles.items():
            if profile.persist.single_result_chars > profile.persist.aggregate_result_chars:
                raise ValueError(
                    f"runtime.compression_profiles.{name} has single_result_chars > aggregate_result_chars"
                )
            if not 0 < profile.autocompact.max_history_share < 1:
                raise ValueError(
                    f"runtime.compression_profiles.{name} has invalid max_history_share"
                )
            if not (
                0 < profile.pressure.yellow_pct
                < profile.pressure.orange_pct
                < profile.pressure.red_pct
                < profile.pressure.hard_stop_pct
                < 1
            ):
                raise ValueError(
                    f"runtime.compression_profiles.{name} has invalid pressure thresholds"
                )

        for name, profile in self.session_profiles.items():
            if profile.child_default_budget_profile not in self.turn_profiles:
                raise ValueError(
                    "runtime.session_profiles."
                    f"{name}.child_default_budget_profile references unknown turn profile "
                    f"'{profile.child_default_budget_profile}'"
                )
        return self


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
    terminal_default_workdir: str = Field(
        default="",
        description="Default working directory for terminal commands (empty = use workspace path from workspace.path config)"
    )


class AliyunOpensearchSearchParams(BaseModel):
    """Aliyun OpenSearch search parameters."""
    
    default_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Default number of search results to return"
    )
    query_rewrite: bool = Field(
        default=True,
        description="Whether to enable query rewriting using LLM"
    )
    content_type: Literal["snippet", "full"] = Field(
        default="snippet",
        description="Content type: 'snippet' for summary or 'full' for complete content"
    )


class AliyunOpensearchConfig(BaseModel):
    """Aliyun OpenSearch configuration.
    
    Provides high-quality Chinese real-time search capability.
    """
    
    api_key: str = Field(..., description="API Key from Aliyun console")
    host: str = Field(..., description="Service host URL (public or VPC)")
    workspace: str = Field(default="default", description="Workspace name")
    enabled: bool = Field(default=True, description="Whether to enable Aliyun OpenSearch")
    search_params: AliyunOpensearchSearchParams = Field(
        default_factory=AliyunOpensearchSearchParams,
        description="Search parameter configuration"
    )


class AgentModelConfig(BaseModel):
    """Agent-specific model configuration."""
    
    name: str = Field(default="", description="Model configuration name to use")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Temperature parameter")
    max_tokens: int | None = Field(default=None, ge=1, description="Maximum tokens to generate")


class AgentConfig(BaseModel):
    """Agent configuration - defines an AI agent."""
    
    id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Display name")
    type: Literal["main", "specialized"] = Field(default="main", description="Agent type")
    persona: str = Field(default="", description="System prompt/persona description")
    workspace: str = Field(default="", description="Agent workspace directory path")
    features: str = Field(default="", description="Feature tags, comma-separated (e.g., 'code-review,daily-summary')")
    model: AgentModelConfig = Field(default_factory=AgentModelConfig, description="Model configuration")
    enable_memory: bool = Field(default=True, description="Whether to enable memory")
    enable_plan: bool = Field(default=False, description="Whether to enable plan mode")
    enable_context_compression: bool = Field(default=True, description="Whether to enable context compression")
    enable_experience_learning: bool = Field(default=True, description="Whether to enable experience learning")


class PeerMatch(BaseModel):
    """Peer matching condition for agent binding."""
    
    kind: Literal["user", "group", "channel"] = Field(..., description="Peer kind: user, group, or channel")
    id: str = Field(..., description="Peer ID (e.g., user ID, group ID, or '*' for wildcard)")

class BindingMatch(BaseModel):
    """Binding match condition."""
    
    channel: str = Field(..., description="Channel ID to match")
    peer: PeerMatch = Field(..., description="Peer matching condition")

class AgentBinding(BaseModel):
    """Agent binding configuration - defines which agent handles messages from specific channel/peer combinations."""
    
    agent_id: str = Field(..., description="Agent ID to bind to")
    match: BindingMatch = Field(..., description="Match condition for this binding")

class ChannelConfig(BaseModel):
    """Channel configuration - defines how users interact with agents.
    
    Note: agent_id is kept for backward compatibility with web/cli channels.
    For third-party channels (telegram, slack, etc.), use bindings instead.
    """
    
    id: str = Field(..., description="Unique channel identifier")
    type: str = Field(..., description="Channel type (web, slack, email, etc.)")
    protocol: Literal["websocket", "webhook", "smtp", "http", "stream"] = Field(default="websocket", description="Communication protocol")
    agent_id: str | None = Field(default=None, description="Associated agent ID (for backward compatibility)")
    default_user: str = Field(default="admin", description="Default user for this channel")
    enabled: bool = Field(default=True, description="Whether this channel is enabled")
    config: dict[str, Any] = Field(default_factory=dict, description="Channel-specific configuration")


class MultiAgentConfig(BaseModel):
    """Multi-agent configuration.
    
    Defines agents, channels, and bindings, loaded from x-agent.yaml.
    Replaces database-stored Agent/Channel entities.
    
    Binding Logic:
    - For web/cli channels: use channel.agent_id (backward compatible)
    - For third-party channels: use bindings to match channel + peer -> agent
    """
    
    agents: list[AgentConfig] = Field(default_factory=list, description="List of agent configurations")
    channels: list[ChannelConfig] = Field(default_factory=list, description="List of channel configurations")
    bindings: list[AgentBinding] = Field(default_factory=list, description="List of agent bindings")
    
    def get_agent(self, agent_id: str) -> AgentConfig | None:
        """Get agent by ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
    
    def get_agent_by_name(self, name: str) -> AgentConfig | None:
        """Get agent by name."""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None
    
    def get_channels_for_agent(self, agent_id: str) -> list[ChannelConfig]:
        """Get all channels for a specific agent (backward compatible)."""
        return [ch for ch in self.channels if ch.agent_id == agent_id]
    
    def get_channel(self, channel_id: str) -> ChannelConfig | None:
        """Get channel by ID."""
        for ch in self.channels:
            if ch.id == channel_id:
                return ch
        return None
    
    def get_enabled_channels(self) -> list[ChannelConfig]:
        """Get all enabled channels."""
        return [ch for ch in self.channels if ch.enabled]
    
    def resolve_agent_for_channel(self, channel_id: str, peer_id: str | None = None, peer_kind: str = "user") -> str | None:
        """Resolve agent ID for a channel and peer.
        
        Priority:
        1. If channel has agent_id set, use it (backward compatibility for web/cli)
        2. If bindings defined, match by channel + peer
        3. Return None if no match
        
        Args:
            channel_id: Channel ID
            peer_id: Peer ID (user ID, group ID, etc.)
            peer_kind: Peer kind (user, group, channel)
        
        Returns:
            Agent ID or None
        """
        channel = self.get_channel(channel_id)
        
        # Priority 1: Check channel.agent_id (backward compatibility)
        if channel and channel.agent_id:
            return channel.agent_id
        
        # Priority 2: Match bindings
        for binding in self.bindings:
            if binding.match.channel != channel_id:
                continue
            
            # Check peer match
            if binding.match.peer.kind == peer_kind:
                if binding.match.peer.id == "*" or binding.match.peer.id == peer_id:
                    return binding.agent_id
        
        return None
    
    def get_bindings_for_channel(self, channel_id: str) -> list[AgentBinding]:
        """Get all bindings for a specific channel."""
        return [b for b in self.bindings if b.match.channel == channel_id]
    
    @model_validator(mode="after")
    def validate_agent_references(self) -> "MultiAgentConfig":
        """Ensure all channel agent_id and binding agent_id references exist."""
        agent_ids = {agent.id for agent in self.agents}
        
        # Validate channel.agent_id references
        for channel in self.channels:
            if channel.agent_id and channel.agent_id not in agent_ids:
                raise ValueError(f"Channel '{channel.id}' references unknown agent '{channel.agent_id}'")
        
        # Validate binding agent_id references
        for binding in self.bindings:
            if binding.agent_id not in agent_ids:
                raise ValueError(f"Binding references unknown agent '{binding.agent_id}'")
            
            # Validate binding channel reference
            if not self.get_channel(binding.match.channel):
                raise ValueError(f"Binding references unknown channel '{binding.match.channel}'")
        
        return self


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
    aliyun_opensearch: AliyunOpensearchConfig = Field(default_factory=lambda: AliyunOpensearchConfig(api_key="", host=""), description="Aliyun OpenSearch config")
    cron: dict[str, Any] = Field(default_factory=dict, description="Cron scheduler config")
    multi_agent: MultiAgentConfig = Field(default_factory=MultiAgentConfig, description="Multi-agent configuration")
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig, description="Runtime control-plane configuration")
