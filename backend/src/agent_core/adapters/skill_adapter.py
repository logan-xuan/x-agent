"""XAgentSkillAdapter - 适配 X-Agent 技能系统到 SkillPort.

将 X-Agent 的技能系统 (SkillRegistry, SkillAdapter) 包装为
agent_core 的 SkillPort Protocol。

核心功能:
- 技能发现: 关键词匹配 + 语义向量搜索
- 技能执行: 委托给 SkillAdapter
- Prompt 生成: 为匹配的技能生成 system prompt 注入内容

OpenClaw 风格优化:
- XML 格式技能列表: <available_skills> 紧凑格式
- 懒加载策略: 只注入路径，按需读取 SKILL.md
- 路径压缩: ~ 替换 home 目录节省 tokens
- 自适应截断: 数量限制 + 字符数限制 + 二分搜索
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..ports.skill_port import (
    SkillCategory,
    SkillContext,
    SkillMetadata,
    SkillResult,
    SkillStatus,
)
from ..types import AgentTool

if TYPE_CHECKING:
    from ...models.skill import SkillManifest
    from ...services.skill.adapter import SkillAdapter
    from ...services.skill.registry import SkillRegistry


# ============================================================================
# OpenClaw 风格常量配置
# ============================================================================

# 技能数量限制
MAX_SKILLS_IN_PROMPT = 150
# 技能列表最大字符数
MAX_SKILLS_PROMPT_CHARS = 30_000
# 单个 SKILL.md 最大字节数
MAX_SKILL_FILE_BYTES = 256_000

# 强制性技能指令模板 (OpenClaw 风格)
SKILL_INSTRUCTION_TEMPLATE = """## Skills (mandatory)

⚠️ **CRITICAL**: Skills are NOT tools. You cannot call skills directly.

Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: use `read_file` to read its SKILL.md at <location>, then follow the instructions inside.
- If multiple could apply: choose the most specific one, read it with `read_file`, then follow it.
- If none clearly apply: proceed without reading any SKILL.md.

**Constraints (MUST follow)**:
1. NEVER try to call a skill name as a tool (e.g., do NOT call "pptx" as a tool)
2. Skills only provide instructions - you must READ them first with `read_file`
3. After reading SKILL.md, follow its instructions exactly (usually involves `run_in_terminal`)
4. Never read more than one SKILL.md upfront

{skills_xml}
"""


class XAgentSkillAdapter:
    """SkillPort 适配器，包装 X-Agent 技能系统.
    
    连接 agent_core 与 X-Agent 的技能系统，提供：
    - 技能发现（关键词 + 语义搜索）
    - 技能执行
    - System Prompt 注入内容生成
    
    Example:
        from src.services.skill.registry import get_skill_registry
        from src.services.skill.adapter import SkillAdapter
        
        registry = get_skill_registry()
        skill_adapter = SkillAdapter(registry=registry)
        
        adapter = XAgentSkillAdapter(
            registry=registry,
            skill_adapter=skill_adapter,
        )
        
        # 匹配技能
        matched = adapter.match_skills("帮我制作一个 PPT")
        
        # 生成 prompt 注入
        prompt = adapter.build_skill_prompt(matched)
    """

    def __init__(
        self,
        registry: SkillRegistry,
        skill_adapter: SkillAdapter | None = None,
    ) -> None:
        """初始化适配器.
        
        Args:
            registry: 技能注册表
            skill_adapter: 技能适配器（可选，用于执行）
        """
        self._registry = registry
        self._skill_adapter = skill_adapter

        # 缓存技能关键词索引
        self._keyword_index: dict[str, list[str]] = {}
        self._index_built = False

    def _build_keyword_index(self) -> None:
        """构建关键词索引，用于快速匹配."""
        if self._index_built:
            return

        self._keyword_index.clear()

        for manifest in self._registry.list_skills():
            skill_id = manifest.skill_id

            # 收集所有关键词
            keywords = set()

            # 从 keywords 字段
            for kw in manifest.keywords:
                keywords.add(kw.lower())

            # 从 tags 字段
            for tag in manifest.tags:
                keywords.add(tag.lower())

            # 从 name 和 description
            keywords.add(manifest.name.lower())

            # 添加到索引
            for kw in keywords:
                if kw not in self._keyword_index:
                    self._keyword_index[kw] = []
                self._keyword_index[kw].append(skill_id)

        self._index_built = True

    def match_skills(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.3,
    ) -> list[SkillManifest]:
        """匹配技能.
        
        使用两阶段匹配:
        1. 精确命令匹配 (/skill)
        2. 关键词 + 语义匹配
        
        Args:
            query: 用户查询
            top_k: 最大返回数量
            min_score: 最小匹配分数
        
        Returns:
            匹配的技能清单列表（按相关度排序）
        """
        # 阶段 1: 精确命令匹配
        if query.startswith("/"):
            command = query.split()[0][1:]  # 去掉 /
            manifest = self._registry.get_skill(command)
            if manifest:
                return [manifest]

        # 阶段 2: 关键词匹配
        self._build_keyword_index()

        query_lower = query.lower()
        scores: dict[str, float] = {}

        # 关键词匹配评分
        for keyword, skill_ids in self._keyword_index.items():
            if keyword in query_lower:
                for skill_id in skill_ids:
                    if skill_id not in scores:
                        scores[skill_id] = 0.0
                    # 根据关键词长度加权
                    scores[skill_id] += len(keyword) / len(query_lower)

        # 检查 auto-trigger 技能
        for manifest in self._registry.list_skills():
            if manifest.auto_trigger:
                # 检查描述中的关键词
                desc_lower = manifest.description.lower()
                if any(word in desc_lower for word in query_lower.split() if len(word) > 2):
                    if manifest.skill_id not in scores:
                        scores[manifest.skill_id] = 0.0
                    scores[manifest.skill_id] += 0.2

        # 过滤和排序
        matched: list[tuple[str, float]] = [
            (skill_id, score)
            for skill_id, score in scores.items()
            if score >= min_score
        ]
        matched.sort(key=lambda x: (-x[1], x[0]))  # 按分数降序，skill_id 升序

        # 获取 manifest
        results: list[SkillManifest] = []
        for skill_id, _ in matched[:top_k]:
            manifest = self._registry.get_skill(skill_id)
            if manifest:
                results.append(manifest)

        return results

    def match_skills_by_intent(
        self,
        query: str,
    ) -> SkillManifest | None:
        """根据意图匹配单个最佳技能.
        
        专门用于自动触发场景，返回最匹配的一个技能。
        
        Args:
            query: 用户输入
        
        Returns:
            最匹配的技能，或 None
        """
        # 定义意图关键词映射
        intent_keywords = {
            "pptx": ["ppt", "演示文稿", "幻灯片", "presentation", "slides", "报告演讲"],
            "pdf": ["pdf", "文档转换", "pdf转换"],
            "docx": ["word", "文档", "docx", "doc"],
            "xlsx": ["excel", "表格", "xlsx", "电子表格", "spreadsheet"],
        }

        query_lower = query.lower()

        # 检查意图关键词
        for skill_id, keywords in intent_keywords.items():
            for kw in keywords:
                if kw in query_lower:
                    manifest = self._registry.get_skill(skill_id)
                    if manifest and manifest.auto_trigger:
                        return manifest

        # 回退到通用匹配
        matched = self.match_skills(query, top_k=1, min_score=0.5)
        return matched[0] if matched else None

    # ========================================================================
    # OpenClaw 风格: XML 格式技能列表 + 懒加载
    # ========================================================================

    def _compact_path(self, file_path: str) -> str:
        """路径压缩: 用 ~ 替换 home 目录.
        
        节省约 5-6 tokens/路径 × N 个技能 ≈ 400-600 tokens。
        
        Example:
            /Users/alice/.x-agent/skills/pptx/SKILL.md
            → ~/.x-agent/skills/pptx/SKILL.md
        
        Args:
            file_path: 原始文件路径
        
        Returns:
            压缩后的路径
        """
        home = os.path.expanduser("~")
        if not home:
            return file_path

        # 确保 home 以路径分隔符结尾
        if not home.endswith(os.sep):
            home = home + os.sep

        if file_path.startswith(home):
            return "~/" + file_path[len(home):]

        return file_path

    def format_skills_for_prompt(
        self,
        skills: list[SkillManifest],
    ) -> str:
        """生成 XML 格式技能列表 (OpenClaw 风格).
        
        只包含 name/description/location，不包含完整 SKILL.md 内容。
        模型需要用 read_file 按需读取 SKILL.md。
        
        Example:
            <available_skills>
              <skill>
                <name>pptx</name>
                <description>PowerPoint toolkit using Node.js</description>
                <location>~/.x-agent/skills/pptx/SKILL.md</location>
              </skill>
            </available_skills>
        
        Args:
            skills: 技能清单列表
        
        Returns:
            XML 格式的技能列表字符串
        """
        if not skills:
            return ""

        lines = ["<available_skills>"]

        for skill in skills:
            # 获取 SKILL.md 路径
            location = ""
            if skill.path:
                skill_md = skill.path / "SKILL.md"
                if skill_md.exists():
                    location = self._compact_path(str(skill_md))

            # 截断过长的描述
            description = skill.description or skill.name
            if len(description) > 200:
                description = description[:197] + "..."

            lines.extend([
                "  <skill>",
                f"    <name>{skill.skill_id}</name>",
                f"    <description>{description}</description>",
                f"    <location>{location}</location>",
                "  </skill>",
            ])

        lines.append("</available_skills>")
        return "\n".join(lines)

    def apply_skills_prompt_limits(
        self,
        skills: list[SkillManifest],
    ) -> tuple[list[SkillManifest], bool, str | None]:
        """应用技能列表截断限制.
        
        两阶段截断:
        1. 数量限制: 最多 MAX_SKILLS_IN_PROMPT 个
        2. 字符数限制: 使用二分搜索找最大可用前缀
        
        Args:
            skills: 原始技能列表
        
        Returns:
            (截断后的技能列表, 是否被截断, 截断原因)
        """
        total = len(skills)

        # 阶段 1: 数量限制
        by_count = skills[:MAX_SKILLS_IN_PROMPT]
        truncated = total > len(by_count)
        truncated_reason = "count" if truncated else None

        # 阶段 2: 字符数限制
        def fits(subset: list[SkillManifest]) -> bool:
            return len(self.format_skills_for_prompt(subset)) <= MAX_SKILLS_PROMPT_CHARS

        if not fits(by_count):
            # 二分搜索找最大可用前缀
            lo, hi = 0, len(by_count)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(by_count[:mid]):
                    lo = mid
                else:
                    hi = mid - 1
            by_count = by_count[:lo]
            truncated = True
            truncated_reason = "chars"

        return by_count, truncated, truncated_reason

    def build_skills_xml_prompt(
        self,
        skills: list[SkillManifest] | None = None,
    ) -> str:
        """构建完整的 Skills Section (OpenClaw 风格).
        
        包含:
        1. 强制性技能指令 (## Skills (mandatory))
        2. XML 格式技能列表
        
        如果不传 skills，则使用所有可用技能。
        
        Args:
            skills: 技能列表，None 表示使用所有技能
        
        Returns:
            完整的 Skills Section 字符串
        """
        # 如果没有传入，获取所有技能
        if skills is None:
            skills = self._registry.list_skills()

        if not skills:
            return ""

        # 应用截断限制
        skills_truncated, truncated, reason = self.apply_skills_prompt_limits(skills)

        # 生成 XML 格式列表
        skills_xml = self.format_skills_for_prompt(skills_truncated)

        # 添加截断警告
        if truncated:
            warning = f"\n<!-- Skills truncated: showing {len(skills_truncated)} of {len(skills)} ({reason}) -->"
            skills_xml = skills_xml + warning

        # 组装完整的 Skills Section
        return SKILL_INSTRUCTION_TEMPLATE.format(skills_xml=skills_xml)

    def build_skill_prompt(
        self,
        skills: list[SkillManifest],
        include_full_content: bool = False,
    ) -> str:
        """为匹配的技能生成 System Prompt 注入内容.
        
        Args:
            skills: 技能清单列表
            include_full_content: 是否包含完整 SKILL.md 内容
        
        Returns:
            格式化的 prompt 内容
        """
        if not skills:
            return ""

        prompt_parts = ["# 可用技能"]
        prompt_parts.append("以下技能可用于处理用户请求：\n")

        for skill in skills:
            prompt_parts.append(f"## {skill.name} (/{skill.skill_id})")
            prompt_parts.append(f"- 描述: {skill.description}")

            if skill.keywords:
                prompt_parts.append(f"- 关键词: {', '.join(skill.keywords)}")

            if skill.examples:
                prompt_parts.append(f"- 示例: {', '.join(skill.examples[:3])}")

            # 加载完整内容
            if include_full_content and skill.path:
                skill_md = skill.path / "SKILL.md"
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        # 移除 frontmatter
                        content = self._strip_frontmatter(content)
                        prompt_parts.append(f"\n### 详细说明\n{content}")
                    except Exception:
                        pass

            prompt_parts.append("")

        return "\n".join(prompt_parts)

    def _strip_frontmatter(self, content: str) -> str:
        """移除 YAML frontmatter."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def load_skill_content(self, skill_id: str) -> str | None:
        """加载技能的完整 SKILL.md 内容.
        
        Args:
            skill_id: 技能 ID
        
        Returns:
            SKILL.md 内容（不含 frontmatter），或 None
        """
        manifest = self._registry.get_skill(skill_id)
        if not manifest or not manifest.path:
            return None

        skill_md = manifest.path / "SKILL.md"
        if not skill_md.exists():
            return None

        try:
            content = skill_md.read_text(encoding="utf-8")
            return self._strip_frontmatter(content)
        except Exception:
            return None

    # ========================================================================
    # SkillPort Protocol 实现
    # ========================================================================

    async def register(
        self,
        metadata: SkillMetadata,
        executor: Callable[[SkillContext], Awaitable[SkillResult]],
    ) -> bool:
        """注册技能（暂不支持动态注册）."""
        # TODO: 支持动态注册
        return False

    async def unregister(self, skill_id: str) -> bool:
        """注销技能（暂不支持）."""
        return False

    async def discover(
        self,
        category: SkillCategory | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
    ) -> list[SkillMetadata]:
        """发现技能.
        
        Args:
            category: 按分类筛选
            tags: 按标签筛选
            query: 搜索查询
        
        Returns:
            匹配的技能元数据列表
        """
        if query:
            matched = self.match_skills(query)
            return [self._convert_to_metadata(m) for m in matched]

        # 无查询时返回所有技能
        all_skills = self._registry.list_skills()

        # 按标签过滤
        if tags:
            all_skills = [
                s for s in all_skills
                if any(t in s.tags for t in tags)
            ]

        return [self._convert_to_metadata(m) for m in all_skills]

    async def execute(
        self,
        skill_id: str,
        context: SkillContext,
    ) -> SkillResult:
        """执行技能."""
        if not self._skill_adapter:
            return SkillResult(
                success=False,
                error="Skill adapter not configured",
            )

        try:
            result = await self._skill_adapter.execute(
                skill_id=skill_id,
                session_id=context.session_id,
                params=context.parameters,
                user_input=context.user_input,
            )
            return SkillResult(
                success=result.success,
                output=result.output or "",
                error=result.error or "",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
            )

    async def get_tools(self, skill_id: str) -> list[AgentTool]:
        """获取技能提供的工具."""
        # TODO: 从技能清单解析工具定义
        return []

    async def get_status(self, skill_id: str) -> SkillStatus:
        """获取技能状态."""
        manifest = self._registry.get_skill(skill_id)
        if manifest:
            return SkillStatus.ACTIVE
        return SkillStatus.DISABLED

    def _convert_to_metadata(self, manifest: SkillManifest) -> SkillMetadata:
        """将 SkillManifest 转换为 SkillMetadata."""
        # 映射分类
        category = SkillCategory.UTILITY
        if manifest.domains:
            domain = manifest.domains[0].lower()
            if "document" in domain or "pdf" in domain or "ppt" in domain:
                category = SkillCategory.DOCUMENT
            elif "search" in domain:
                category = SkillCategory.SEARCH
            elif "code" in domain:
                category = SkillCategory.CODE

        return SkillMetadata(
            skill_id=manifest.skill_id,
            name=manifest.name,
            description=manifest.description,
            version=manifest.version,
            category=category,
            tags=manifest.tags,
            author=manifest.vendor or "",
        )

    def invalidate_cache(self) -> None:
        """使缓存失效，下次访问时重新构建索引."""
        self._index_built = False
        self._keyword_index.clear()
        self._registry.clear_cache()


def create_skill_adapter() -> XAgentSkillAdapter | None:
    """创建技能适配器的便捷方法.
    
    自动初始化 SkillRegistry 和 SkillAdapter。
    
    Returns:
        XAgentSkillAdapter 实例，或初始化失败时返回 None
    """
    try:
        from ...config.manager import ConfigManager
        from ...services.skill.adapter import SkillAdapter
        from ...services.skill.registry import init_skill_registry
        from ...utils.logger import get_logger

        logger = get_logger(__name__)

        # 获取配置路径
        config = ConfigManager().config
        workspace_path = Path(config.workspace.path).expanduser()

        # 技能目录
        user_skills_dir = workspace_path / "skills"
        # 修复: 正确的路径是 src/skills，而不是 backend/skills
        # skill_adapter.py 在 src/agent_core/adapters/
        # parent -> adapters, parent.parent -> agent_core, parent.parent.parent -> src
        system_skills_dir = Path(__file__).parent.parent.parent / "skills"

        logger.debug(
            "Initializing skill adapter",
            extra={
                "user_skills_dir": str(user_skills_dir),
                "system_skills_dir": str(system_skills_dir),
            }
        )

        # 初始化注册表
        registry = init_skill_registry(
            user_skills_dir=user_skills_dir,
            system_skills_dir=system_skills_dir,
        )

        # 创建内部适配器
        skill_adapter = SkillAdapter(registry=registry)

        return XAgentSkillAdapter(
            registry=registry,
            skill_adapter=skill_adapter,
        )
    except Exception as e:
        # 记录详细错误以便调试
        try:
            from ...utils.logger import get_logger
            logger = get_logger(__name__)
            logger.error(
                "Failed to create skill adapter",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
        except Exception:
            pass
        return None
