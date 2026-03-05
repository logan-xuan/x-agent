"""X-Agent 技能元数据模型。

定义技能系统的数据结构，遵循 X-Agent Skills 规范。

核心实体:
- SkillManifest: 完整技能定义（40+ 字段）
- SkillSource: 技能注册来源（USER > SYSTEM）
- RiskLevel, DataAccessLevel, ApprovalMode, ExecutionStage: 枚举类型
- SkillCapabilityVector: 语义搜索用嵌入向量
- SkillSearchContext: 发现输入上下文
- SkillCard: 发现输出格式
- SkillExecutionContext/Result: 执行运行时模型
- SkillScore: 多维度评分明细
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any


# =============================================================================
# 枚举类型 (T008-T009)
# =============================================================================


class RiskLevel(str, Enum):
    """技能执行风险等级。
    
    决定确认要求和执行策略。
    """
    LOW = "low"  # 只读，无副作用
    MEDIUM = "medium"  # 文件修改、内容创建
    HIGH = "high"  # 删除、外部请求、代码执行
    CRITICAL = "critical"  # 系统操作、安全相关


class DataAccessLevel(str, Enum):
    """技能操作的数据访问级别。"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"


class ApprovalMode(str, Enum):
    """技能执行审批模式。
    
    控制用户确认的处理方式。
    """
    AUTO = "auto"  # 自动执行
    CONFIRM = "confirm"  # 需要用户确认
    APPROVAL = "approval"  # 需要审批流程
    MANUAL = "manual"  # 仅手动触发


class ExecutionStage(str, Enum):
    """渐进式技能执行的阶段。
    
    支持试运行、计划生成和回滚能力。
    """
    DRY_RUN = "dry_run"  # 模拟执行
    PLAN = "plan"  # 生成执行计划
    CONFIRM = "confirm"  # 等待用户确认
    COMMIT = "commit"  # 执行操作
    ROLLBACK = "rollback"  # 撤销操作


class SkillSource(IntEnum):
    """技能注册来源（含优先级）。
    
    数值越小优先级越高。
    同 skill_id 时 USER 技能覆盖 SYSTEM 技能。
    """
    USER = 100  # 用户/工作区级别（最高优先级）
    SYSTEM = 200  # 系统内置


# =============================================================================
# SkillManifest (T010 - 核心实体)
# =============================================================================


@dataclass
class SkillManifest:
    """完整的技能清单定义。
    
    核心数据模型，包含所有技能元数据。
    映射自 manifest.json 或从 SKILL.md frontmatter 解析。
    
    必需字段: skill_id, name, version, description
    """
    # 身份标识
    skill_id: str
    name: str
    version: str
    description: str
    vendor: str | None = None
    signature: str | None = None
    
    # 能力描述
    description_detail: str | None = None
    tags: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    
    # 输入输出契约
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    error_schema: dict[str, Any] | None = None
    
    # 执行配置
    endpoint: str | None = None
    callable: str | None = None
    timeout_ms: int = 30000
    max_retries: int = 3
    idempotency: bool = False
    
    # 约束条件
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    os: list[str] = field(default_factory=list)
    requires_bins: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)
    requires_config: list[str] = field(default_factory=list)
    
    # 风险与策略
    risk_level: RiskLevel = RiskLevel.LOW
    data_access: DataAccessLevel = DataAccessLevel.READ_ONLY
    side_effect: bool = False
    required_auth: list[str] = field(default_factory=list)
    approval_mode: ApprovalMode = ApprovalMode.AUTO
    always: bool = False
    auto_trigger: bool = True
    user_invocable: bool = True
    disable_model_invocation: bool = False
    
    # 可观测性
    telemetry: bool = True
    trace_fields: list[str] = field(default_factory=list)
    redaction_rules: list[str] = field(default_factory=list)
    
    # 渐进式执行
    stages: list[ExecutionStage] = field(default_factory=list)
    supports_dry_run: bool = False
    supports_rollback: bool = False
    
    # 目录结构（运行时元数据）
    path: Path | None = None
    has_scripts: bool = False
    has_references: bool = False
    has_assets: bool = False
    
    # 展示信息
    emoji: str | None = None
    homepage: str | None = None
    
    # 遗留兼容
    keywords: list[str] = field(default_factory=list)
    argument_hint: str | None = None
    allowed_tools: list[str] | None = None
    forbidden_tools: list[str] = field(default_factory=list)
    context: str | None = None
    license: str | None = None
    priority: int = 999
    
    # 扩展字段
    extra: dict[str, Any] = field(default_factory=dict)
    
    # 校验正则
    _SKILL_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
    _VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+.*$")
    
    def __post_init__(self) -> None:
        """初始化后校验清单。"""
        self._validate_skill_id()
        self._validate_version()
        self._validate_name()
        self._validate_description()
    
    def _validate_skill_id(self) -> None:
        """校验 skill_id 格式。"""
        if not self.skill_id:
            raise ValueError("skill_id is required")
        if len(self.skill_id) > 64:
            raise ValueError(f"skill_id too long: {len(self.skill_id)} > 64")
        if not self._SKILL_ID_PATTERN.match(self.skill_id):
            raise ValueError(
                f"skill_id must be kebab-case (lowercase, numbers, hyphens): {self.skill_id}"
            )
    
    def _validate_version(self) -> None:
        """校验版本号是否遵循 semver。"""
        if not self.version:
            raise ValueError("version is required")
        if not self._VERSION_PATTERN.match(self.version):
            raise ValueError(
                f"version must follow semver format (e.g., 1.0.0): {self.version}"
            )
    
    def _validate_name(self) -> None:
        """校验名称。"""
        if not self.name:
            raise ValueError("name is required")
        if len(self.name) > 128:
            raise ValueError(f"name too long: {len(self.name)} > 128")
    
    def _validate_description(self) -> None:
        """校验描述。"""
        if not self.description:
            raise ValueError("description is required")
        if len(self.description) > 1024:
            raise ValueError(f"description too long: {len(self.description)} > 1024")
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        result: dict[str, Any] = {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
        
        # 可选身份字段
        if self.vendor:
            result["vendor"] = self.vendor
        if self.signature:
            result["signature"] = self.signature
        
        # 能力描述
        if self.description_detail:
            result["description_detail"] = self.description_detail
        if self.tags:
            result["tags"] = self.tags
        if self.domains:
            result["domains"] = self.domains
        if self.examples:
            result["examples"] = self.examples
        
        # 输入输出契约
        if self.input_schema:
            result["input_schema"] = self.input_schema
        if self.output_schema:
            result["output_schema"] = self.output_schema
        if self.error_schema:
            result["error_schema"] = self.error_schema
        
        # 执行配置
        if self.endpoint:
            result["endpoint"] = self.endpoint
        if self.callable:
            result["callable"] = self.callable
        result["timeout_ms"] = self.timeout_ms
        result["max_retries"] = self.max_retries
        result["idempotency"] = self.idempotency
        
        # 风险与策略
        result["risk_level"] = self.risk_level.value
        result["data_access"] = self.data_access.value
        result["side_effect"] = self.side_effect
        result["approval_mode"] = self.approval_mode.value
        result["auto_trigger"] = self.auto_trigger
        result["user_invocable"] = self.user_invocable
        
        # 渐进式执行
        result["supports_dry_run"] = self.supports_dry_run
        result["supports_rollback"] = self.supports_rollback
        
        # 目录结构
        if self.path:
            result["path"] = str(self.path)
        result["has_scripts"] = self.has_scripts
        result["has_references"] = self.has_references
        result["has_assets"] = self.has_assets
        
        # 展示信息
        if self.emoji:
            result["emoji"] = self.emoji
        if self.homepage:
            result["homepage"] = self.homepage
        
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        """从字典创建 SkillManifest。"""
        # 解析枚举
        risk_level = data.get("risk_level", "low")
        if isinstance(risk_level, str):
            risk_level = RiskLevel(risk_level)
        
        data_access = data.get("data_access", "read_only")
        if isinstance(data_access, str):
            data_access = DataAccessLevel(data_access)
        
        approval_mode = data.get("approval_mode", "auto")
        if isinstance(approval_mode, str):
            approval_mode = ApprovalMode(approval_mode)
        
        # 解析路径
        path = data.get("path")
        if path and isinstance(path, str):
            path = Path(path)
        
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            version=data["version"],
            description=data["description"],
            vendor=data.get("vendor"),
            signature=data.get("signature"),
            description_detail=data.get("description_detail"),
            tags=data.get("tags", []),
            domains=data.get("domains", []),
            examples=data.get("examples", []),
            input_schema=data.get("input_schema"),
            output_schema=data.get("output_schema"),
            error_schema=data.get("error_schema"),
            endpoint=data.get("endpoint"),
            callable=data.get("callable"),
            timeout_ms=data.get("timeout_ms", 30000),
            max_retries=data.get("max_retries", 3),
            idempotency=data.get("idempotency", False),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            invariants=data.get("invariants", []),
            os=data.get("os", []),
            requires_bins=data.get("requires_bins", []),
            requires_env=data.get("requires_env", []),
            requires_config=data.get("requires_config", []),
            risk_level=risk_level,
            data_access=data_access,
            side_effect=data.get("side_effect", False),
            required_auth=data.get("required_auth", []),
            approval_mode=approval_mode,
            always=data.get("always", False),
            auto_trigger=data.get("auto_trigger", True),
            user_invocable=data.get("user_invocable", True),
            disable_model_invocation=data.get("disable_model_invocation", False),
            telemetry=data.get("telemetry", True),
            trace_fields=data.get("trace_fields", []),
            redaction_rules=data.get("redaction_rules", []),
            supports_dry_run=data.get("supports_dry_run", False),
            supports_rollback=data.get("supports_rollback", False),
            path=path,
            has_scripts=data.get("has_scripts", False),
            has_references=data.get("has_references", False),
            has_assets=data.get("has_assets", False),
            emoji=data.get("emoji"),
            homepage=data.get("homepage"),
            keywords=data.get("keywords", []),
            argument_hint=data.get("argument_hint"),
            allowed_tools=data.get("allowed_tools"),
            forbidden_tools=data.get("forbidden_tools", []),
            context=data.get("context"),
            license=data.get("license"),
            priority=data.get("priority", 999),
        )


# =============================================================================
# 搜索上下文 (T011)
# =============================================================================


@dataclass
class SearchBudget:
    """技能搜索的预算约束。"""
    max_latency_ms: int = 1000
    max_cost: float = 0.01


@dataclass
class SkillSearchContext:
    """技能发现的输入上下文。
    
    包含用户意图和可用参数，用于技能匹配。
    """
    user_input: str
    available_params: dict[str, Any] = field(default_factory=dict)
    user_permissions: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    budget: SearchBudget | None = None


# =============================================================================
# SkillCard (T012)
# =============================================================================


@dataclass
class SkillCard:
    """技能发现输出格式。
    
    提供技能选择的决策支持信息。
    """
    # 基本信息
    skill_id: str
    name: str
    description: str
    emoji: str | None = None
    
    # 匹配信息
    relevance_score: float = 0.0
    match_reason: str = ""
    
    # 风险与策略
    risk_level: RiskLevel = RiskLevel.LOW
    side_effect: bool = False
    approval_mode: ApprovalMode = ApprovalMode.AUTO
    approval_required: bool = False
    
    # 参数信息
    input_schema: dict[str, Any] | None = None
    required_params: list[str] = field(default_factory=list)
    available_params: list[str] = field(default_factory=list)
    missing_params: list[str] = field(default_factory=list)
    schema_fit_score: float = 0.0
    
    # 执行选项
    supports_dry_run: bool = False
    supports_rollback: bool = False
    
    # 预估
    estimated_latency_ms: int = 0
    estimated_cost: float = 0.0
    
    # 快速参考
    quick_reference: str = ""
    when_to_use: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "emoji": self.emoji,
            "relevance_score": self.relevance_score,
            "match_reason": self.match_reason,
            "risk_level": self.risk_level.value,
            "side_effect": self.side_effect,
            "approval_mode": self.approval_mode.value,
            "approval_required": self.approval_required,
            "input_schema": self.input_schema,
            "required_params": self.required_params,
            "available_params": self.available_params,
            "missing_params": self.missing_params,
            "schema_fit_score": self.schema_fit_score,
            "supports_dry_run": self.supports_dry_run,
            "supports_rollback": self.supports_rollback,
            "estimated_latency_ms": self.estimated_latency_ms,
            "estimated_cost": self.estimated_cost,
            "quick_reference": self.quick_reference,
            "when_to_use": self.when_to_use,
        }


# =============================================================================
# 执行上下文 (T013)
# =============================================================================


@dataclass
class SkillExecutionContext:
    """技能执行运行时上下文。"""
    # 会话信息
    session_id: str
    conversation_id: str = ""
    
    # 用户信息
    user_input: str = ""
    user_permissions: list[str] = field(default_factory=list)
    
    # 参数
    params: dict[str, Any] = field(default_factory=dict)
    missing_params: list[str] = field(default_factory=list)
    
    # 执行阶段
    stage: ExecutionStage = ExecutionStage.COMMIT
    dry_run: bool = False
    auto_confirm: bool = False
    
    # 状态
    state: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    
    # 追踪
    trace_id: str = ""
    parent_span_id: str = ""


# =============================================================================
# 执行结果 (T014)
# =============================================================================


@dataclass
class SkillExecutionResult:
    """技能执行结果。"""
    success: bool
    stage: ExecutionStage = ExecutionStage.COMMIT
    
    # 输出
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    
    # 错误
    error: str = ""
    error_code: str = ""
    recoverable: bool = False
    
    # 回滚信息
    rollback_available: bool = False
    rollback_data: dict[str, Any] = field(default_factory=dict)
    
    # 遥测
    duration_ms: int = 0
    tokens_used: int = 0
    
    # 确认状态
    confirmation_pending: bool = False
    confirmation_message: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "stage": self.stage.value,
            "output": self.output,
            "data": self.data,
            "artifacts": self.artifacts,
            "error": self.error,
            "error_code": self.error_code,
            "recoverable": self.recoverable,
            "rollback_available": self.rollback_available,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "confirmation_pending": self.confirmation_pending,
            "confirmation_message": self.confirmation_message,
        }


# =============================================================================
# 技能评分 (T015)
# =============================================================================


@dataclass
class SkillScore:
    """多维度评分结果。
    
    技能相关性在 5 个维度上的评分明细。
    """
    skill_id: str
    total: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    
    # 标准权重
    WEIGHT_SEMANTIC: float = 0.35
    WEIGHT_SCHEMA_FIT: float = 0.25
    WEIGHT_POLICY: float = 0.20
    WEIGHT_LATENCY: float = 0.10
    WEIGHT_RELIABILITY: float = 0.10
    
    def __post_init__(self) -> None:
        """初始化默认评分明细。"""
        if not self.breakdown:
            self.breakdown = {
                "semantic": 0.0,
                "schema_fit": 0.0,
                "policy": 0.0,
                "latency": 0.0,
                "reliability": 0.0,
            }
    
    def calculate_total(self) -> float:
        """计算加权总分。"""
        self.total = (
            self.breakdown.get("semantic", 0.0) * self.WEIGHT_SEMANTIC +
            self.breakdown.get("schema_fit", 0.0) * self.WEIGHT_SCHEMA_FIT +
            self.breakdown.get("policy", 0.0) * self.WEIGHT_POLICY +
            self.breakdown.get("latency", 0.0) * self.WEIGHT_LATENCY +
            self.breakdown.get("reliability", 0.0) * self.WEIGHT_RELIABILITY
        )
        return self.total


# =============================================================================
# 能力向量（用于语义搜索）
# =============================================================================


@dataclass
class SkillCapabilityVector:
    """语义搜索用能力向量。
    
    包含从技能描述生成的嵌入向量。
    """
    skill_id: str
    capability_text: str
    tool_signature: str = ""
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = "m3e-small"
    embedding_updated_at: datetime | None = None
    keywords: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


# =============================================================================
# 遗留兼容 - SkillMetadata
# =============================================================================


@dataclass
class SkillMetadata:
    """遗留技能元数据（向后兼容）。
    
    已弃用: 请使用 SkillManifest。
    保留此类仅为兼容现有代码。
    """
    name: str
    description: str
    path: Path
    
    # 目录结构
    has_scripts: bool = False
    has_references: bool = False
    has_assets: bool = False
    
    # 可选字段
    disable_model_invocation: bool = False
    user_invocable: bool = True
    argument_hint: str | None = None
    allowed_tools: list[str] | None = None
    forbidden_tools: list[str] = field(default_factory=list)
    context: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)
    auto_trigger: bool = True
    priority: int = 999
    extra: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """校验元数据。"""
        if not self.name:
            raise ValueError("Skill name is required")
        if len(self.name) > 64:
            raise ValueError(f"Skill name too long: {len(self.name)} > 64")
        if not all(c.islower() or c.isdigit() or c in "-_" for c in self.name):
            raise ValueError(
                f"Skill name must be lowercase alphanumeric with hyphens: {self.name}"
            )
        if not self.description:
            raise ValueError("Skill description is required")
        if len(self.description) > 1024:
            raise ValueError(f"Skill description too long: {len(self.description)} > 1024")
    
    def to_manifest(self) -> SkillManifest:
        """转换为 SkillManifest。"""
        return SkillManifest(
            skill_id=self.name,
            name=self.name,
            version="1.0.0",
            description=self.description,
            path=self.path,
            has_scripts=self.has_scripts,
            has_references=self.has_references,
            has_assets=self.has_assets,
            disable_model_invocation=self.disable_model_invocation,
            user_invocable=self.user_invocable,
            argument_hint=self.argument_hint,
            allowed_tools=self.allowed_tools,
            forbidden_tools=self.forbidden_tools,
            context=self.context,
            license=self.license,
            keywords=self.keywords,
            auto_trigger=self.auto_trigger,
            priority=self.priority,
            extra=self.extra,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "has_scripts": self.has_scripts,
            "has_references": self.has_references,
            "has_assets": self.has_assets,
            "disable_model_invocation": self.disable_model_invocation,
            "user_invocable": self.user_invocable,
            "argument_hint": self.argument_hint,
            "allowed_tools": self.allowed_tools,
            "forbidden_tools": self.forbidden_tools,
            "keywords": self.keywords,
            "context": self.context,
            "license": self.license,
            "auto_trigger": self.auto_trigger,
            "priority": self.priority,
            **self.extra,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMetadata":
        """从字典创建。"""
        return cls(
            name=data["name"],
            description=data["description"],
            path=Path(data["path"]),
            has_scripts=data.get("has_scripts", False),
            has_references=data.get("has_references", False),
            has_assets=data.get("has_assets", False),
            disable_model_invocation=data.get("disable_model_invocation", False),
            user_invocable=data.get("user_invocable", True),
            argument_hint=data.get("argument_hint"),
            allowed_tools=data.get("allowed_tools"),
            forbidden_tools=data.get("forbidden_tools", []),
            context=data.get("context"),
            license=data.get("license"),
            keywords=data.get("keywords", []),
            auto_trigger=data.get("auto_trigger", True),
            priority=data.get("priority", 999),
            extra={
                k: v
                for k, v in data.items()
                if k
                not in [
                    "name",
                    "description",
                    "path",
                    "has_scripts",
                    "has_references",
                    "has_assets",
                    "disable_model_invocation",
                    "user_invocable",
                    "argument_hint",
                    "allowed_tools",
                    "forbidden_tools",
                    "context",
                    "license",
                    "keywords",
                    "auto_trigger",
                    "priority",
                ]
            },
        )
