"""
Skill System - 技能发现、注册与执行

核心组件:
- ManifestParser: 解析 manifest.json / SKILL.md
- SkillRegistry: 技能注册与缓存管理
- SkillEmbedder: 生成语义嵌入向量
- SkillScorer: 多维度加权评分
- SkillDiscovery: 语义检索与智能匹配
- SkillExecutor: 风险感知执行引擎
- ProgressiveExecutor: 渐进式多阶段执行
- ParamCompleter: 智能参数补全
- SkillAdapter: 统一对外接口
"""

# Phase 3: Core components - 技能发现与执行
from .manifest_parser import ManifestParser, ManifestParseError, parse_manifest
from .registry import (
    SkillRegistry,
    get_skill_registry,
    init_skill_registry,
    reset_skill_registry,
)

# Phase 4: Semantic search components
from .embedder import SkillEmbedder, EmbeddingResult, get_embedder
from .scorer import SkillScorer
from .discovery import SkillDiscovery, get_discovery

# Phase 5: Risk control
from .executor import SkillExecutor, PermissionCheckResult, PreconditionCheckResult

# Phase 6: Progressive execution
from .progressive import ProgressiveExecutor, StageResult

# Phase 7: Parameter completion
from .param_completer import ParamCompleter, CompletionResult

# Phase 8: Integration adapter
from .adapter import SkillAdapter

__all__ = [
    # Phase 3: Core
    "ManifestParser",
    "ManifestParseError",
    "parse_manifest",
    "SkillRegistry",
    "get_skill_registry",
    "init_skill_registry",
    "reset_skill_registry",
    # Phase 4: Semantic search
    "SkillEmbedder",
    "EmbeddingResult",
    "get_embedder",
    "SkillScorer",
    "SkillDiscovery",
    "get_discovery",
    # Phase 5: Execution
    "SkillExecutor",
    "PermissionCheckResult",
    "PreconditionCheckResult",
    # Phase 6: Progressive
    "ProgressiveExecutor",
    "StageResult",
    # Phase 7: Param completion
    "ParamCompleter",
    "CompletionResult",
    # Phase 8: Integration
    "SkillAdapter",
]
