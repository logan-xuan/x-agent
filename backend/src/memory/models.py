"""Memory system data models.

This module defines the data structures for the memory system:
- SpiritConfig: AI personality configuration
- OwnerProfile: User profile and preferences
- ToolDefinition: Tool and capability definitions
- MemoryEntry: Individual memory records
- DailyLog: Daily log organization
- SessionType: Session type enumeration (main vs shared)
- FileLoadResult: File loading result
- ContextFile: Context file definition
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MemoryContentType(str, Enum):
    """Memory entry content types."""
    CONVERSATION = "conversation"
    DECISION = "decision"
    SUMMARY = "summary"
    MANUAL = "manual"


class SessionType(str, Enum):
    """Session type enumeration for context loading.
    
    Determines which context files are loaded:
    - MAIN: Single user conversation, can load MEMORY.md
    - SHARED: Group chat/multi-user context, blocks MEMORY.md for privacy
    """
    MAIN = "main"          # 主会话：单用户对话，可加载 MEMORY.md
    SHARED = "shared"      # 共享上下文：群聊/多用户，禁止加载 MEMORY.md


class SpiritConfig(BaseModel):
    """AI personality configuration from SPIRIT.md.
    
    Defines who the AI is, its personality, values, and behavior rules.
    """
    role: str = Field(default="", description="AI 角色定位")
    personality: str = Field(default="", description="AI 性格特征")
    values: list[str] = Field(default_factory=list, description="AI 价值观")
    behavior_rules: list[str] = Field(default_factory=list, description="AI 行为准则")
    file_path: str | None = Field(default=None, description="源文件路径")
    last_modified: datetime | None = Field(default=None, description="最后修改时间")

    model_config = {
        "extra": "ignore",
    }


class OwnerProfile(BaseModel):
    """User profile from OWNER.md.
    
    Defines who the user is, their preferences, goals, and habits.
    """
    name: str = Field(default="用户", description="用户姓名")
    age: int | None = Field(default=None, description="用户年龄")
    occupation: str = Field(default="", description="用户职业")
    interests: list[str] = Field(default_factory=list, description="兴趣爱好")
    goals: list[str] = Field(default_factory=list, description="当前目标")
    preferences: dict[str, str] = Field(default_factory=dict, description="偏好设置")
    file_path: str | None = Field(default=None, description="源文件路径")
    last_modified: datetime | None = Field(default=None, description="最后修改时间")

    model_config = {
        "extra": "ignore",
    }


class IdentityConfig(BaseModel):
    """AI identity from IDENTITY.md.
    
    Defines who the AI is - its name, form, style, etc.
    """
    name: str = Field(default="", description="AI名字")
    form: str = Field(default="", description="存在形式")
    style: str = Field(default="", description="气质风格")
    emoji: str = Field(default="", description="标志性emoji")
    file_path: str | None = Field(default=None, description="源文件路径")
    last_modified: datetime | None = Field(default=None, description="最后修改时间")

    model_config = {
        "extra": "ignore",
    }


class ToolDefinition(BaseModel):
    """Tool definition from TOOLS.md.
    
    Defines a tool or capability that the AI can use.
    """
    name: str = Field(description="工具名称")
    description: str = Field(default="", description="功能描述")
    parameters: dict[str, Any] = Field(default_factory=dict, description="参数规范")
    enabled: bool = Field(default=True, description="是否启用")

    model_config = {
        "extra": "ignore",
    }


class MemoryEntry(BaseModel):
    """Single memory entry.
    
    Represents a single piece of memory with content, metadata, and embedding.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="UUID 唯一标识")
    content: str = Field(description="记忆内容")
    content_type: MemoryContentType = Field(
        default=MemoryContentType.CONVERSATION,
        description="内容类型"
    )
    source_file: str = Field(default="", description="来源文件路径")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    embedding: list[float] | None = Field(default=None, description="向量嵌入")

    model_config = {
        "extra": "ignore",
        "use_enum_values": True,
    }

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now()


class DailyLog(BaseModel):
    """Daily log organization.
    
    Groups memory entries by date for easy retrieval.
    """
    date: str = Field(description="日志日期 (YYYY-MM-DD)")
    file_path: str = Field(default="", description="文件路径")
    entries: list[str] = Field(default_factory=list, description="当日记忆条目 ID 列表")
    summary: str = Field(default="", description="当日摘要")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    model_config = {
        "extra": "ignore",
    }


class ContextBundle(BaseModel):
    """Bundled context for AI response.
    
    Contains all loaded context information for generating AI responses.
    Extended with session type for privacy-aware context loading.
    """
    spirit: SpiritConfig | None = Field(default=None, description="AI 人格配置")
    identity: IdentityConfig | None = Field(default=None, description="AI 身份（名字等）")
    owner: OwnerProfile | None = Field(default=None, description="用户画像")
    tools: list[ToolDefinition] = Field(default_factory=list, description="工具定义")
    recent_logs: list[DailyLog] = Field(default_factory=list, description="近期日志")
    long_term_memory: str = Field(default="", description="长期记忆")
    loaded_at: datetime = Field(default_factory=datetime.now, description="加载时间")
    
    # New fields for agent guidance
    session_type: SessionType = Field(default=SessionType.MAIN, description="会话类型")
    session_id: str | None = Field(default=None, description="会话标识")
    loaded_files: list[str] = Field(default_factory=list, description="已加载文件列表")
    load_time_ms: int = Field(default=0, description="加载耗时（毫秒）")

    model_config = {
        "extra": "ignore",
    }


class IdentityStatus(BaseModel):
    """Identity initialization status."""
    initialized: bool = Field(default=False, description="是否已初始化")
    has_spirit: bool = Field(default=False, description="是否有 SPIRIT.md")
    has_owner: bool = Field(default=False, description="是否有 OWNER.md")


class IdentityInitRequest(BaseModel):
    """Request for identity initialization."""
    owner_name: str = Field(description="用户姓名")
    owner_occupation: str | None = Field(default=None, description="用户职业")
    owner_interests: list[str] = Field(default_factory=list, description="兴趣爱好")
    ai_role: str | None = Field(default=None, description="AI 角色定位")
    ai_personality: str | None = Field(default=None, description="AI 性格特征")


class IdentityInitResponse(BaseModel):
    """Response for identity initialization."""
    success: bool = Field(description="是否成功")
    spirit: SpiritConfig | None = Field(default=None, description="AI 人格配置")
    owner: OwnerProfile | None = Field(default=None, description="用户画像")


class FileLoadResult(BaseModel):
    """Result of a file loading operation.
    
    Used to track the status and details of each file loaded during context building.
    """
    file_path: str = Field(description="文件路径")
    success: bool = Field(description="是否成功")
    content: str | None = Field(default=None, description="文件内容（成功时）")
    error: str | None = Field(default=None, description="错误信息（失败时）")
    loaded_at: datetime = Field(default_factory=datetime.now, description="加载时间")
    from_cache: bool = Field(default=False, description="是否来自缓存")
    is_default: bool = Field(default=False, description="是否使用默认模板创建")
    content_length: int = Field(default=0, description="内容长度")

    model_config = {
        "extra": "ignore",
    }


class ContextFile(BaseModel):
    """Definition of a context file.
    
    Describes a file that can be loaded as part of the agent's context.
    """
    name: str = Field(description="文件名（如 AGENTS.md）")
    path: str = Field(description="相对路径（如 workspace/AGENTS.md）")
    required: bool = Field(default=False, description="是否必需")
    main_session_only: bool = Field(default=False, description="是否仅在主会话加载")
    load_order: int = Field(default=0, description="加载顺序（越小越先加载）")
    default_template: str | None = Field(default=None, description="默认模板内容")

    model_config = {
        "extra": "ignore",
    }


# Predefined context files configuration
CONTEXT_FILES: list[ContextFile] = [
    ContextFile(
        name="AGENTS.md",
        path="workspace/AGENTS.md",
        required=True,
        main_session_only=False,
        load_order=1,
    ),
    ContextFile(
        name="SPIRIT.md",
        path="workspace/SPIRIT.md",
        required=True,
        main_session_only=False,
        load_order=2,
    ),
    ContextFile(
        name="OWNER.md",
        path="workspace/OWNER.md",
        required=True,
        main_session_only=False,
        load_order=3,
    ),
    ContextFile(
        name="TOOLS.md",
        path="workspace/TOOLS.md",
        required=False,
        main_session_only=False,
        load_order=4,
    ),
    ContextFile(
        name="MEMORY.md",
        path="workspace/MEMORY.md",
        required=False,
        main_session_only=True,  # Only load in main session
        load_order=7,
    ),
]
