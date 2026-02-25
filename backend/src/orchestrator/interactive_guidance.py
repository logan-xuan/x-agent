"""Interactive User Guidance System for X-Agent.

核心能力:
1. 问题可视化 (Problem Visualization)
2. 交互式引导 (Interactive Guidance)
3. 自动修正建议 (Auto-Fix Suggestions)
4. 实时验证反馈 (Real-time Validation)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Callable
import json
import time


class ProblemSeverity(Enum):
    """问题严重程度分级."""
    CRITICAL = "critical"  # 任务无法继续
    HIGH = "high"  # 严重阻碍
    MEDIUM = "medium"  # 可以绕过但影响效率
    LOW = "low"  # 轻微影响


class ProblemType(Enum):
    """问题类型分类."""
    SCRIPT_NOT_FOUND = "script_not_found"
    PERMISSION_DENIED = "permission_denied"
    INVALID_PARAMETER = "invalid_parameter"
    DEPENDENCY_MISSING = "dependency_missing"
    CONFIG_ERROR = "config_error"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    TIMEOUT = "timeout"
    LLM_NOT_CALLING_TOOLS = "llm_not_calling_tools"  # 🔥 NEW: LLM 不调用工具
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class InteractiveStep:
    """交互式引导步骤."""
    step_number: int
    title: str
    description: str
    command: Optional[str] = None  # 可执行命令
    expected_output: Optional[str] = None  # 期望输出
    user_action_required: bool = False  # 是否需要用户操作
    validation_regex: Optional[str] = None  # 验证正则
    
    def to_dict(self) -> Dict:
        return {
            "step": self.step_number,
            "title": self.title,
            "description": self.description,
            "command": self.command,
            "expected_output": self.expected_output,
            "user_action_required": self.user_action_required,
        }


@dataclass
class ProblemReport:
    """问题诊断报告."""
    problem_type: ProblemType
    severity: ProblemSeverity
    title: str
    description: str
    detected_at: float = field(default_factory=time.time)
    context: Dict = field(default_factory=dict)
    
    # 交互式引导步骤
    interactive_steps: List[InteractiveStep] = field(default_factory=list)
    
    # 自动修正建议
    auto_fix_suggestions: List[str] = field(default_factory=list)
    
    # 用户补充信息提示
    user_info_requests: List[str] = field(default_factory=list)
    
    def add_step(self, step: InteractiveStep):
        """添加引导步骤."""
        self.interactive_steps.append(step)
    
    def add_auto_fix(self, suggestion: str):
        """添加自动修正建议."""
        self.auto_fix_suggestions.append(suggestion)
    
    def request_user_info(self, request: str):
        """请求用户补充信息."""
        self.user_info_requests.append(request)
    
    def to_visualization(self) -> Dict:
        """转换为可视化格式."""
        return {
            "type": self.problem_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at,
            "context": self.context,
            "steps": [s.to_dict() for s in self.interactive_steps],
            "auto_fixes": self.auto_fix_suggestions,
            "user_info_needed": self.user_info_requests,
        }


class InteractiveGuidanceGenerator:
    """交互式指引生成器."""
    
    def __init__(self):
        self.problem_templates = self._load_problem_templates()
    
    def _load_problem_templates(self) -> Dict[ProblemType, Dict]:
        """加载问题模板库."""
        return {
            ProblemType.SCRIPT_NOT_FOUND: {
                "title": "脚本文件不存在",
                "severity": ProblemSeverity.CRITICAL,
                "description": "系统找不到指定的脚本文件，可能是因为：\n"
                              "1. 脚本路径配置错误\n"
                              "2. 脚本尚未创建或同步\n"
                              "3. 文件名拼写错误",
                "icon": "📁",
            },
            ProblemType.PERMISSION_DENIED: {
                "title": "权限不足",
                "severity": ProblemSeverity.HIGH,
                "description": "没有足够的权限执行此操作，可能需要：\n"
                              "1. 修改文件权限\n"
                              "2. 使用 sudo 执行\n"
                              "3. 检查用户组配置",
                "icon": "🔒",
            },
            ProblemType.INVALID_PARAMETER: {
                "title": "参数无效",
                "severity": ProblemSeverity.MEDIUM,
                "description": "提供的参数不符合要求，请检查：\n"
                              "1. 参数格式是否正确\n"
                              "2. 参数值是否在有效范围\n"
                              "3. 必需参数是否缺失",
                "icon": "⚙️",
            },
            ProblemType.DEPENDENCY_MISSING: {
                "title": "缺少依赖",
                "severity": ProblemSeverity.HIGH,
                "description": "缺少必要的依赖项，需要安装：\n"
                              "1. Python 包\n"
                              "2. 系统工具\n"
                              "3. 外部服务",
                "icon": "📦",
            },
            # 🔥 NEW: LLM not calling tools template
            ProblemType.LLM_NOT_CALLING_TOOLS: {
                "title": "LLM 未调用工具",
                "severity": ProblemSeverity.HIGH,
                "description": "系统检测到用户问题需要调用工具，但 LLM 未能正确识别并调用相应工具",
                "icon": "🤖",
            },
            ProblemType.UNKNOWN_ERROR: {
                "title": "未知错误",
                "severity": ProblemSeverity.MEDIUM,
                "description": "发生了未预期的错误，系统将提供通用故障排除指引",
                "icon": "❓",
            },
        }
    
    def generate_guidance(
        self,
        error_type: str,
        error_message: str,
        context: Dict,
    ) -> ProblemReport:
        """根据错误生成交互式指引."""
        
        # 映射错误类型
        problem_type = self._map_error_type(error_type)
        
        # 映射错误类型
        problem_type = self._map_error_type(error_type)
        
        # Safely get template with fallback
        try:
            template = self.problem_templates.get(
                problem_type,
                self.problem_templates.get(ProblemType.UNKNOWN_ERROR, {
                    "title": "未知错误",
                    "severity": ProblemSeverity.MEDIUM,
                    "description": "发生了未预期的错误",
                    "icon": "❓",
                })
            )
        except Exception:
            # Ultimate fallback if ProblemType.UNKNOWN_ERROR itself fails
            template = {
                "title": "执行错误",
                "severity": ProblemSeverity.HIGH,
                "description": "系统发生错误",
                "icon": "⚠️",
            }
        
        # 创建报告
        report = ProblemReport(
            problem_type=problem_type,
            severity=template["severity"],
            title=template["title"],
            description=template["description"],
            context=context,
        )
        
        # 添加图标到描述
        report.description = f"{template['icon']} {report.description}"
        
        # 生成具体的引导步骤
        self._generate_interactive_steps(report, error_message, context)
        
        # 生成自动修正建议
        self._generate_auto_fixes(report, error_message, context)
        
        # 生成用户信息请求
        self._generate_user_info_requests(report, context)
        
        return report
    
    def _map_error_type(self, error_type: str) -> ProblemType:
        """映射错误类型到标准分类."""
        mapping = {
            "tool_not_found": ProblemType.SCRIPT_NOT_FOUND,
            "file_not_found": ProblemType.SCRIPT_NOT_FOUND,
            "permission_denied": ProblemType.PERMISSION_DENIED,
            "access_denied": ProblemType.PERMISSION_DENIED,
            "invalid_parameter": ProblemType.INVALID_PARAMETER,
            "missing_argument": ProblemType.INVALID_PARAMETER,
            "module_not_found": ProblemType.DEPENDENCY_MISSING,
            "import_error": ProblemType.DEPENDENCY_MISSING,
            "llm_not_calling_tools": ProblemType.LLM_NOT_CALLING_TOOLS,
            "command_not_found": ProblemType.DEPENDENCY_MISSING,
        }
        return mapping.get(error_type, ProblemType.UNKNOWN_ERROR)
    
    def _generate_interactive_steps(
        self, 
        report: ProblemReport,
        error_message: str,
        context: Dict,
    ):
        """生成交互式引导步骤."""
        
        if report.problem_type == ProblemType.SCRIPT_NOT_FOUND:
            script_path = context.get("script_path", "未知路径")
            
            report.add_step(InteractiveStep(
                step_number=1,
                title="确认脚本路径",
                description=f"请检查脚本是否存在于以下路径:\n`{script_path}`",
                command=f"ls -la {script_path}",
                expected_output="文件详细信息或 'No such file'",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=2,
                title="检查技能目录结构",
                description="查看技能目录下有哪些可用的脚本:",
                command=f"ls -la $(dirname {script_path})",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=3,
                title="选择解决方案",
                description="根据检查结果选择:\n"
                          "- 如果文件存在 → 检查权限和路径\n"
                          "- 如果文件不存在 → 创建或指定正确的脚本",
                user_action_required=True,
            ))
        
        elif report.problem_type == ProblemType.PERMISSION_DENIED:
            file_path = context.get("file_path", "未知文件")
            
            report.add_step(InteractiveStep(
                step_number=1,
                title="查看当前权限",
                description=f"检查文件权限设置:",
                command=f"ls -l {file_path}",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=2,
                title="修复权限（可选）",
                description="如果需要，可以执行以下命令修复权限:",
                command=f"chmod +x {file_path}",
                user_action_required=False,  # 提供选项但不强制
            ))
            
            report.add_step(InteractiveStep(
                step_number=3,
                title="重新尝试执行",
                description="权限修复后重新运行:",
                command=context.get("original_command", ""),
                user_action_required=True,
            ))
        
        elif report.problem_type == ProblemType.INVALID_PARAMETER:
            report.add_step(InteractiveStep(
                step_number=1,
                title="查看参数说明",
                description="查看命令的正确用法:",
                command=context.get("command", "") + " --help",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=2,
                title="修正参数并重试",
                description="根据帮助信息修正参数后重新执行",
                user_action_required=True,
            ))
    
        
        elif report.problem_type == ProblemType.INVALID_PARAMETER:
            report.add_step(InteractiveStep(
                step_number=1,
                title="查看参数说明",
                description="查看命令的正确用法:",
                command=context.get("command", "") + " --help",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=2,
                title="修正参数并重试",
                description="根据帮助信息修正参数后重新执行",
                user_action_required=True,
            ))
        
        # 🔥 NEW: LLM not calling tools guidance
        elif report.problem_type == ProblemType.LLM_NOT_CALLING_TOOLS:
            retry_count = context.get("retry_count", 0)
            max_retry = context.get("max_retry", 2)
            
            report.add_step(InteractiveStep(
                step_number=1,
                title="检查用户问题是否需要工具",
                description=f"系统检测到用户问题需要调用工具，但 LLM 已连续{retry_count}次未识别（上限：{max_retry}次）",
                user_action_required=False,
            ))
            
            report.add_step(InteractiveStep(
                step_number=2,
                title="尝试重新描述问题",
                description="请更明确地说明你需要使用的工具或执行的操作，例如:\n"
                          "- \"请使用 web_search 搜索...\"\n"
                          "- \"帮我运行 python 脚本...\"\n"
                          "- \"调用 pdf 工具处理...\"",
                user_action_required=True,
            ))
            
            report.add_step(InteractiveStep(
                step_number=3,
                title="查看可用工具列表",
                description="查看当前有哪些工具可以使用:",
                command="ls -la skills/",
                user_action_required=True,
            ))
    
    def _generate_auto_fixes(
        self,
        report: ProblemReport,
        error_message: str,
        context: Dict,
    ):
        """生成自动修正建议."""
        
        if report.problem_type == ProblemType.SCRIPT_NOT_FOUND:
            script_dir = context.get("skill_scripts_dir", "")
            if script_dir:
                report.add_auto_fix(f"在技能目录创建默认脚本：`cd {script_dir} && touch script.py`")
                report.add_auto_fix("使用其他可用脚本替代")
                report.add_auto_fix("从模板库复制示例脚本")
        
        elif report.problem_type == ProblemType.PERMISSION_DENIED:
            file_path = context.get("file_path", "")
            if file_path:
                report.add_auto_fix(f"自动修复权限：`chmod +x {file_path}`")
                report.add_auto_fix("使用 sudo 执行（需要确认）")
        
        elif report.problem_type == ProblemType.DEPENDENCY_MISSING:
            package = context.get("missing_package", "")
            if package:
                report.add_auto_fix(f"安装依赖：`pip install {package}`")
                report.add_auto_fix("更新 requirements.txt")
    
    
    def _generate_user_info_requests(
        self,
        report: ProblemReport,
        context: Dict,
    ):
        """生成需要用户补充的信息请求."""
        
        if report.problem_type == ProblemType.SCRIPT_NOT_FOUND:
            report.request_user_info("请提供正确的脚本路径或名称")
            report.request_user_info("是否有其他可用的替代脚本？")
            report.request_user_info("是否需要我帮你创建默认脚本？")
        
        elif report.problem_type == ProblemType.INVALID_PARAMETER:
            report.request_user_info("请提供完整的命令和参数")
            report.request_user_info("期望的输入格式是什么？")
            report.request_user_info("有参考示例可以提供吗？")
        
        elif report.problem_type == ProblemType.DEPENDENCY_MISSING:
            report.request_user_info("是否可以安装新依赖？")
            report.request_user_info("有特定的版本要求吗？")
        
        # 🔥 NEW: LLM not calling tools user info requests
        elif report.problem_type == ProblemType.LLM_NOT_CALLING_TOOLS:
            report.request_user_info("请更明确地描述你需要使用的工具")
            report.request_user_info("你的具体目标是什么？（搜索、计算、处理文件等）")
            report.request_user_info("是否有特定的技能或脚本想要使用？")
            report.request_user_info("是否需要使用虚拟环境？")
    
    def create_visualization_json(
        self,
        report: ProblemReport,
    ) -> str:
        """创建可视化的 JSON 输出."""
        return json.dumps(report.to_visualization(), indent=2, ensure_ascii=False)
    
    def create_markdown_guidance(
        self,
        report: ProblemReport,
    ) -> str:
        """创建 Markdown 格式的指引."""
        lines = []
        
        # 标题和严重程度
        severity_emoji = {
            ProblemSeverity.CRITICAL: "🚨",
            ProblemSeverity.HIGH: "⚠️",
            ProblemSeverity.MEDIUM: "⚡",
            ProblemSeverity.LOW: "ℹ️",
        }
        
        lines.append(f"{severity_emoji[report.severity]} **{report.title}**")
        lines.append("")
        lines.append(f"**类型**: `{report.problem_type.value}`")
        lines.append(f"**严重程度**: {report.severity.value}")
        lines.append("")
        
        # 问题描述
        lines.append("### 📋 问题描述")
        lines.append(report.description)
        lines.append("")
        
        # 上下文信息
        if report.context:
            lines.append("### 🔍 上下文信息")
            for key, value in report.context.items():
                lines.append(f"- **{key}**: `{value}`")
            lines.append("")
        
        # 交互式步骤
        if report.interactive_steps:
            lines.append("### 🎯 交互式引导步骤")
            lines.append("")
            for step in report.interactive_steps:
                lines.append(f"**Step {step.step_number}**: {step.title}")
                lines.append(step.description)
                if step.command:
                    lines.append(f"```bash\n{step.command}\n```")
                if step.expected_output:
                    lines.append(f"*期望输出*: {step.expected_output}")
                lines.append("")
        
        # 自动修正建议
        if report.auto_fix_suggestions:
            lines.append("### 🔧 自动修正建议")
            for i, fix in enumerate(report.auto_fix_suggestions, 1):
                lines.append(f"{i}. {fix}")
            lines.append("")
        
        # 用户信息请求
        if report.user_info_requests:
            lines.append("### 💬 需要你补充的信息")
            for i, request in enumerate(report.user_info_requests, 1):
                lines.append(f"{i}. ❓ {request}")
            lines.append("")
        
        return "\n".join(lines)


# Example usage and demonstration
if __name__ == "__main__":
    print("=" * 80)
    print("Interactive User Guidance System - Demo")
    print("=" * 80)
    
    generator = InteractiveGuidanceGenerator()
    
    # Test Case 1: Script not found
    print("\n" + "=" * 80)
    print("Test Case 1: Script Not Found Error")
    print("=" * 80)
    
    error_context_1 = {
        "script_path": "/workspace/skills/pdf/scripts/create_pdf.py",
        "skill_scripts_dir": "/workspace/skills/pdf/scripts",
        "original_command": "python /workspace/skills/pdf/scripts/create_pdf.py",
    }
    
    report_1 = generator.generate_guidance(
        error_type="tool_not_found",
        error_message="Script '/workspace/skills/pdf/scripts/create_pdf.py' not found",
        context=error_context_1,
    )
    
    print("\n📄 Markdown Guidance:")
    print(generator.create_markdown_guidance(report_1))
    
    print("\n📊 JSON Visualization:")
    print(generator.create_visualization_json(report_1))
    
    # Test Case 2: Permission denied
    print("\n" + "=" * 80)
    print("Test Case 2: Permission Denied Error")
    print("=" * 80)
    
    error_context_2 = {
        "file_path": "/workspace/skills/pdf/scripts/generate_report.sh",
        "original_command": "bash /workspace/skills/pdf/scripts/generate_report.sh",
        "current_user": "xuan.lx",
    }
    
    report_2 = generator.generate_guidance(
        error_type="permission_denied",
        error_message="Permission denied: cannot execute '/workspace/skills/pdf/scripts/generate_report.sh'",
        context=error_context_2,
    )
    
    print("\n📄 Markdown Guidance:")
    print(generator.create_markdown_guidance(report_2)[:1000])
    
    print("\n" + "=" * 80)
    print("✅ Demo completed!")
    print("=" * 80)
