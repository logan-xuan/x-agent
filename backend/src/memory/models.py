"""Memory system data models.

This module defines the data structures for the memory system:
- SpiritConfig: AI personality configuration
- OwnerProfile: User profile and preferences
- ToolDefinition: Tool and capability definitions
- MemoryEntry: Individual memory records
- DailyLog: Daily log organization
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
    """
    spirit: SpiritConfig | None = Field(default=None, description="AI 人格配置")
    owner: OwnerProfile | None = Field(default=None, description="用户画像")
    tools: list[ToolDefinition] = Field(default_factory=list, description="工具定义")
    recent_logs: list[DailyLog] = Field(default_factory=list, description="近期日志")
    long_term_memory: str = Field(default="", description="长期记忆")
    loaded_at: datetime = Field(default_factory=datetime.now, description="加载时间")

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
