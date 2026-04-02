"""技能系统接口定义.

SkillPort 定义了 agent_core 与技能系统交互的接口。
支持技能注册、发现、执行等能力。

扩展点说明:
    实现者可以接入不同的技能系统：
    - 内置技能（默认）
    - 外部技能仓库
    - 动态加载的插件技能
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..types import AgentTool


class SkillCategory(Enum):
    """技能分类."""

    DOCUMENT = "document"      # 文档处理
    SEARCH = "search"          # 搜索相关
    CODE = "code"              # 代码相关
    COMMUNICATION = "communication"  # 通信相关
    AUTOMATION = "automation"  # 自动化
    ANALYSIS = "analysis"      # 分析类
    CREATIVE = "creative"      # 创意类
    UTILITY = "utility"        # 工具类


class SkillStatus(Enum):
    """技能状态."""

    REGISTERED = "registered"  # 已注册
    LOADED = "loaded"          # 已加载
    ACTIVE = "active"          # 活跃中
    DISABLED = "disabled"      # 已禁用
    ERROR = "error"            # 错误状态


@dataclass
class SkillMetadata:
    """技能元数据.
    
    Attributes:
        skill_id: 技能唯一标识
        name: 显示名称
        description: 技能描述
        version: 版本号
        category: 分类
        tags: 标签列表
        author: 作者
        requires: 依赖的其他技能
        provides_tools: 提供的工具列表
        config_schema: 配置项 schema
    """

    skill_id: str = ""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: SkillCategory = SkillCategory.UTILITY
    tags: list[str] = field(default_factory=list)
    author: str = ""
    requires: list[str] = field(default_factory=list)
    provides_tools: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    """技能执行上下文.
    
    Attributes:
        session_id: 会话ID
        user_input: 用户输入
        parameters: 技能参数
        state: 状态数据
        config: 配置项
    """

    session_id: str = ""
    user_input: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    """技能执行结果.
    
    Attributes:
        success: 是否成功
        output: 输出内容
        artifacts: 生成的产物（文件、数据等）
        next_action: 下一步动作提示（可选）
        error: 错误信息
    """

    success: bool = True
    output: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    next_action: str = ""
    error: str = ""


class SkillPort(Protocol):
    """技能系统接口.
    
    agent_core 通过此接口管理和执行技能。
    实现者需要提供注册、发现、执行等能力。
    
    Example:
        class SimpleSkillManager:
            def __init__(self):
                self._skills: dict[str, SkillMetadata] = {}
            
            async def register(self, metadata, executor):
                self._skills[metadata.skill_id] = {
                    "metadata": metadata,
                    "executor": executor,
                }
            
            async def execute(self, skill_id, context):
                skill = self._skills.get(skill_id)
                if skill:
                    return await skill["executor"](context)
                return SkillResult(success=False, error="Skill not found")
    """

    async def register(
        self,
        metadata: SkillMetadata,
        executor: Callable[[SkillContext], Awaitable[SkillResult]],
    ) -> bool:
        """注册技能.
        
        Args:
            metadata: 技能元数据
            executor: 执行函数
        
        Returns:
            bool: 是否注册成功
        """
        ...

    async def unregister(self, skill_id: str) -> bool:
        """注销技能.
        
        Args:
            skill_id: 技能ID
        
        Returns:
            bool: 是否注销成功
        """
        ...

    async def discover(
        self,
        category: SkillCategory | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
    ) -> list[SkillMetadata]:
        """发现技能.
        
        Args:
            category: 按分类筛选（可选）
            tags: 按标签筛选（可选）
            query: 搜索查询（可选）
        
        Returns:
            list[SkillMetadata]: 匹配的技能列表
        """
        ...

    async def execute(
        self,
        skill_id: str,
        context: SkillContext,
    ) -> SkillResult:
        """执行技能.
        
        Args:
            skill_id: 技能ID
            context: 执行上下文
        
        Returns:
            SkillResult: 执行结果
        
        Raises:
            Exception: 执行失败时抛出异常
        """
        ...

    async def get_tools(self, skill_id: str) -> list[AgentTool]:
        """获取技能提供的工具.
        
        Args:
            skill_id: 技能ID
        
        Returns:
            list[AgentTool]: 工具列表
        """
        ...

    async def get_status(self, skill_id: str) -> SkillStatus:
        """获取技能状态.
        
        Args:
            skill_id: 技能ID
        
        Returns:
            SkillStatus: 技能状态
        """
        ...
