"""技能命令解析与调度模块 (OpenClaw 风格).

实现 Slash 命令解析和双重调度机制:
1. Tool Dispatch: frontmatter 配置 command-dispatch: tool 时直接调用工具
2. Prompt Rewrite: 重写用户输入为技能指令

参考 OpenClaw 的 skill-commands.ts 和 get-reply-inline-actions.ts 设计。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..models.skill import SkillManifest


# ============================================================================
# 数据类型定义
# ============================================================================

@dataclass
class SkillCommandSpec:
    """技能命令规格.
    
    Attributes:
        name: 命令名称 (用于 /command)
        skill_name: 技能名称
        description: 命令描述
        dispatch_kind: 调度类型 ("tool" | None)
        dispatch_tool: Tool Dispatch 时的工具名称
    """
    name: str
    skill_name: str
    description: str
    dispatch_kind: Optional[str] = None
    dispatch_tool: Optional[str] = None


@dataclass
class SkillInvocation:
    """技能调用信息.
    
    Attributes:
        skill_name: 技能名称
        command_name: 命令名称
        args: 用户参数
        dispatch_mode: 调度模式 ("prompt_rewrite" | "tool_dispatch")
        tool_name: Tool Dispatch 时的工具名称
    """
    skill_name: str
    command_name: str
    args: Optional[str]
    dispatch_mode: str  # "prompt_rewrite" | "tool_dispatch"
    tool_name: Optional[str] = None


# ============================================================================
# 保留命令列表 (内置命令不应被技能覆盖)
# ============================================================================

RESERVED_COMMANDS = frozenset([
    "help", "status", "config", "clear", "reset",
    "model", "think", "verbose", "reasoning",
    "memory", "skill", "skills", "tools",
    "abort", "stop", "cancel",
])


# ============================================================================
# 技能命令解析器
# ============================================================================

class SkillCommandResolver:
    """技能命令解析器 (OpenClaw 风格).
    
    解析 Slash 命令格式:
    - /skill_name args  → 直接调用技能
    - /skill pptx args  → 通用技能调用格式
    
    Example:
        resolver = SkillCommandResolver(skill_commands)
        invocation = resolver.resolve("/pptx 请帮我制作一个PPT")
        # SkillInvocation(skill_name="pptx", args="请帮我制作一个PPT", ...)
    """
    
    def __init__(self, skill_commands: list[SkillCommandSpec]) -> None:
        """初始化解析器.
        
        Args:
            skill_commands: 可用的技能命令列表
        """
        # 构建命令名到规格的映射 (小写化便于匹配)
        self._commands: dict[str, SkillCommandSpec] = {}
        for cmd in skill_commands:
            self._commands[cmd.name.lower()] = cmd
            # 同时用 skill_name 作为别名
            if cmd.skill_name.lower() != cmd.name.lower():
                self._commands[cmd.skill_name.lower()] = cmd
    
    def resolve(self, user_input: str) -> Optional[SkillInvocation]:
        """解析用户输入为技能调用.
        
        支持格式:
        - /pptx 请帮我制作PPT
        - /skill pptx 请帮我制作PPT
        - /skill_name args
        
        Args:
            user_input: 用户输入
        
        Returns:
            SkillInvocation 或 None (无匹配)
        """
        trimmed = user_input.strip()
        if not trimmed.startswith("/"):
            return None
        
        # 匹配: /command args (command 不含空格)
        match = re.match(r"^/([^\s]+)(?:\s+([\s\S]+))?$", trimmed)
        if not match:
            return None
        
        command_name = match.group(1).lower()
        args = match.group(2)
        
        # 处理 /skill <skill_name> <args> 格式 (优先于保留命令检查)
        if command_name == "skill" and args:
            skill_match = re.match(r"^([^\s]+)(?:\s+([\s\S]+))?$", args.strip())
            if skill_match:
                actual_skill_name = skill_match.group(1).lower()
                actual_args = skill_match.group(2)
                
                cmd = self._find_command(actual_skill_name)
                if cmd:
                    return self._create_invocation(cmd, actual_args)
            return None
        
        # 检查是否是保留命令 (skill 除外，因为已在上面处理)
        if command_name in RESERVED_COMMANDS:
            return None
        
        # 直接匹配 /skill_name 格式
        cmd = self._find_command(command_name)
        if cmd:
            return self._create_invocation(cmd, args)
        
        return None
    
    def _find_command(self, name: str) -> Optional[SkillCommandSpec]:
        """查找命令规格.
        
        支持模糊匹配:
        - 精确匹配
        - 下划线/连字符互换
        
        Args:
            name: 命令名称 (小写)
        
        Returns:
            SkillCommandSpec 或 None
        """
        # 精确匹配
        if name in self._commands:
            return self._commands[name]
        
        # 尝试下划线/连字符互换
        normalized = self._normalize_command_name(name)
        if normalized in self._commands:
            return self._commands[normalized]
        
        return None
    
    def _normalize_command_name(self, name: str) -> str:
        """规范化命令名称.
        
        将空格和下划线统一转换为连字符。
        
        Args:
            name: 原始名称
        
        Returns:
            规范化后的名称
        """
        return re.sub(r"[\s_]+", "-", name.strip().lower())
    
    def _create_invocation(
        self,
        cmd: SkillCommandSpec,
        args: Optional[str],
    ) -> SkillInvocation:
        """创建技能调用对象.
        
        根据命令规格决定调度模式。
        
        Args:
            cmd: 命令规格
            args: 用户参数
        
        Returns:
            SkillInvocation
        """
        if cmd.dispatch_kind == "tool" and cmd.dispatch_tool:
            return SkillInvocation(
                skill_name=cmd.skill_name,
                command_name=cmd.name,
                args=args.strip() if args else None,
                dispatch_mode="tool_dispatch",
                tool_name=cmd.dispatch_tool,
            )
        
        return SkillInvocation(
            skill_name=cmd.skill_name,
            command_name=cmd.name,
            args=args.strip() if args else None,
            dispatch_mode="prompt_rewrite",
        )
    
    def list_commands(self) -> list[str]:
        """列出所有可用命令.
        
        Returns:
            命令名称列表
        """
        # 去重 (因为 skill_name 可能作为别名)
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd.name)
        return sorted(result)


# ============================================================================
# Prompt Rewrite 调度器
# ============================================================================

class SkillPromptRewriter:
    """技能 Prompt 重写器.
    
    将技能调用重写为强制性指令，确保 LLM 遵循技能。
    
    Example:
        rewriter = SkillPromptRewriter()
        prompt = rewriter.rewrite(invocation)
        # 'Use the "pptx" skill for this request.\n\nUser input:\n请帮我制作PPT'
    """
    
    def rewrite(self, invocation: SkillInvocation) -> str:
        """重写技能调用为 prompt.
        
        生成强制性指令，要求 LLM:
        1. 读取 SKILL.md
        2. 严格遵循指令
        
        Args:
            invocation: 技能调用信息
        
        Returns:
            重写后的 prompt
        """
        parts = [
            f'Use the "{invocation.skill_name}" skill for this request.',
            "",
            "⚠️ IMPORTANT:",
            f"1. First, read the SKILL.md for {invocation.skill_name} skill",
            "2. Follow the instructions in SKILL.md exactly",
            "3. Do NOT use alternative approaches",
        ]
        
        if invocation.args:
            parts.extend([
                "",
                "User input:",
                invocation.args,
            ])
        
        return "\n".join(parts)
    
    def rewrite_simple(self, invocation: SkillInvocation) -> str:
        """简单重写 (用于已经注入了 Skills Section 的场景).
        
        Args:
            invocation: 技能调用信息
        
        Returns:
            重写后的 prompt
        """
        parts = [
            f'Use the "{invocation.skill_name}" skill for this request.',
        ]
        
        if invocation.args:
            parts.extend([
                "",
                "User input:",
                invocation.args,
            ])
        
        return "\n".join(parts)


# ============================================================================
# 从 SkillManifest 构建 SkillCommandSpec
# ============================================================================

def build_skill_command_specs(
    manifests: list["SkillManifest"],
    reserved_names: Optional[set[str]] = None,
) -> list[SkillCommandSpec]:
    """从技能清单构建命令规格列表.
    
    Args:
        manifests: 技能清单列表
        reserved_names: 保留的命令名称
    
    Returns:
        SkillCommandSpec 列表
    """
    reserved = reserved_names or set(RESERVED_COMMANDS)
    used_names: set[str] = set(reserved)
    specs: list[SkillCommandSpec] = []
    
    for manifest in manifests:
        # 生成命令名称
        raw_name = manifest.skill_id
        base_name = _sanitize_command_name(raw_name)
        
        # 确保唯一性
        unique_name = _resolve_unique_name(base_name, used_names)
        used_names.add(unique_name.lower())
        
        # 截断描述
        description = manifest.description or manifest.name
        if len(description) > 100:
            description = description[:97] + "..."
        
        # 解析 frontmatter 中的 dispatch 配置
        dispatch_kind = None
        dispatch_tool = None
        # TODO: 从 manifest.metadata 解析 command-dispatch 和 command-tool
        
        specs.append(SkillCommandSpec(
            name=unique_name,
            skill_name=manifest.skill_id,
            description=description,
            dispatch_kind=dispatch_kind,
            dispatch_tool=dispatch_tool,
        ))
    
    return specs


def _sanitize_command_name(raw: str) -> str:
    """清理命令名称.
    
    - 转小写
    - 非字母数字字符替换为下划线
    - 最大 32 字符
    
    Args:
        raw: 原始名称
    
    Returns:
        清理后的名称
    """
    normalized = raw.lower()
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized[:32] or "skill"


def _resolve_unique_name(base: str, used: set[str]) -> str:
    """生成唯一的命令名称.
    
    如果 base 已被使用，添加数字后缀。
    
    Args:
        base: 基础名称
        used: 已使用的名称集合
    
    Returns:
        唯一名称
    """
    if base.lower() not in used:
        return base
    
    for i in range(2, 1000):
        candidate = f"{base}_{i}"
        if candidate.lower() not in used:
            return candidate
    
    return f"{base}_x"
