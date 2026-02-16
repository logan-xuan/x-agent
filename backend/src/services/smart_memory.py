"""Smart memory service using LLM for intelligent content analysis.

This module provides:
- LLM-based importance detection for memory recording
- Intelligent content extraction for identity files
- Unified entry point to avoid duplicate writes
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..memory.models import MemoryContentType, MemoryEntry
    from ..memory.md_sync import MarkdownSync
    from ..services.llm.router import LLMRouter

logger = get_logger(__name__)

# Prompt for analyzing if content should be recorded to memory
MEMORY_ANALYSIS_PROMPT = """你是一个内容分析专家。分析以下对话内容，判断是否需要记录到记忆系统。

## 用户消息
{user_message}

## AI回复
{assistant_message}

## 判断标准
只有以下情况才需要记录：
1. **重要偏好**：用户明确表达喜欢/不喜欢/偏好
2. **关键决策**：用户做出的重要决定
3. **身份信息**：用户的姓名、职业、习惯等个人信息
4. **重要约定**：计划、承诺、deadline等
5. **明确要求**：用户说"记住这个"、"别忘了"等

**不需要记录的情况**：
- 日常闲聊、问候
- 临时性的内容
- 已经重复记录过的信息
- 无实际意义的对话

## 输出格式（JSON）
{{
  "should_record": true/false,
  "record_type": "memory|identity|skip",
  "extracted_content": "提取的关键内容（简洁，不超过50字）",
  "reason": "判断理由"
}}

注意：只输出JSON，不要有其他内容。"""


# Prompt for extracting identity information
IDENTITY_EXTRACTION_PROMPT = """你是一个信息提取专家。从对话中提取身份相关信息，用于更新AI的身份文件。

## 用户消息
{user_message}

## AI回复  
{assistant_message}

## 重要规则

**只有在用户明确表达要设置/更改身份信息时才提取**：
- 用户说"我叫XXX"、"你就叫我XXX" → 提取用户姓名
- 用户说"你叫XXX"、"我给你起名叫XXX" → 提取AI名字
- 用户说"你是XXX"、"你的角色是XXX" → 提取AI角色

**不要在以下情况提取身份信息**：
- 用户只是在抱怨或询问（如"你怎么又叫错名字了"）
- 用户只是在复述或引用之前的对话内容
- 用户提到名字但不是要更改设置（如"马铁蛋还是虾铁蛋？"）
- 对话中没有明确的设置意图

## 需要提取的信息

### OWNER.md (用户画像)
- 姓名：用户希望被怎么称呼
- 职业/身份
- 兴趣爱好
- 偏好习惯

### SPIRIT.md (AI人格)
- AI名字：用户给AI起的名字
- AI角色定位
- AI性格特点
- 用户期望的行为方式

### IDENTITY.md
- AI名称
- 存在形式
- 气质风格
- 标志性emoji

## 输出格式（JSON）
如果用户明确要求设置/更改身份信息，输出：
{{
  "has_identity_info": true,
  "owner_updates": {{
    "name": "用户姓名或null",
    "occupation": "职业或null",
    "interests": ["兴趣1", "兴趣2"] 或 null,
    "preferences": {{"key": "value"}} 或 null
  }},
  "spirit_updates": {{
    "role": "AI角色定位或null",
    "personality": "性格特点或null",
    "values": ["价值观1"] 或 null,
    "behavior_rules": ["行为准则1"] 或 null
  }},
  "identity_updates": {{
    "name": "AI名字或null",
    "form": "存在形式或null",
    "style": "气质风格或null",
    "emoji": "标志性emoji或null"
  }}
}}

如果用户没有明确要求设置/更改身份信息，输出：
{{
  "has_identity_info": false
}}

注意：只输出JSON，不要有其他内容。"""


class SmartMemoryService:
    """Smart memory service using LLM for intelligent decisions.
    
    This service:
    - Uses LLM to determine if content should be recorded
    - Extracts structured identity information
    - Provides unified entry point to avoid duplicates
    """
    
    def __init__(
        self,
        llm_router: "LLMRouter",
        workspace_path: str = "workspace"
    ) -> None:
        """Initialize smart memory service.
        
        Args:
            llm_router: LLM router for making API calls
            workspace_path: Path to workspace directory
        """
        self._llm_router = llm_router
        self._workspace_path = Path(workspace_path)
        self._last_processed_hash: str | None = None
        
        logger.info(
            "SmartMemoryService initialized",
            extra={"workspace_path": str(workspace_path)}
        )
    
    def _hash_content(self, user_message: str, assistant_message: str) -> str:
        """Create a hash of the content to detect duplicates."""
        import hashlib
        content = f"{user_message}|||{assistant_message}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    async def analyze_and_record(
        self,
        user_message: str,
        assistant_message: str,
        session_id: str,
        md_sync: Any = None
    ) -> dict[str, Any]:
        """Analyze conversation and record if appropriate.
        
        This is the unified entry point that:
        1. Checks for duplicate processing
        2. Uses LLM to analyze importance
        3. Records to memory if appropriate
        4. Updates identity files if appropriate
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
            session_id: Session ID
            md_sync: MarkdownSync instance for writing
            
        Returns:
            Dict with results of the analysis
        """
        result = {
            "recorded": False,
            "identity_updated": False,
            "skip_reason": None,
            "extracted_content": None,
        }
        
        # Check for duplicate processing
        content_hash = self._hash_content(user_message, assistant_message)
        if content_hash == self._last_processed_hash:
            result["skip_reason"] = "duplicate"
            logger.debug("Skipping duplicate content processing")
            return result
        
        self._last_processed_hash = content_hash
        
        try:
            # Step 1: Analyze if should record to memory
            analysis = await self._analyze_importance(user_message, assistant_message)
            
            if analysis.get("should_record") and analysis.get("extracted_content"):
                record_type = analysis.get("record_type", "memory")
                
                if record_type == "memory" and md_sync:
                    # Record to daily memory (delayed import to avoid circular dependency)
                    from ..memory.models import MemoryEntry, MemoryContentType
                    
                    entry = MemoryEntry(
                        content=analysis["extracted_content"],
                        content_type=MemoryContentType.MANUAL,
                        metadata={
                            "session_id": session_id,
                            "record_type": record_type,
                            "reason": analysis.get("reason", ""),
                        }
                    )
                    md_sync.append_memory_entry(entry)
                    result["recorded"] = True
                    result["extracted_content"] = analysis["extracted_content"]
                    
                    # Also update MEMORY.md (long-term memory) in real-time
                    self._update_long_term_memory(analysis["extracted_content"], analysis.get("reason", ""))
                    
                    logger.info(
                        "Content recorded to memory via LLM analysis",
                        extra={
                            "extracted_content": analysis["extracted_content"][:50],
                            "record_type": record_type,
                        }
                    )
            
            # Step 2: Extract identity information
            identity_info = await self._extract_identity(user_message, assistant_message)
            
            if identity_info.get("has_identity_info"):
                updated = self._update_identity_files(identity_info)
                result["identity_updated"] = updated
                
                if updated:
                    logger.info(
                        "Identity files updated via LLM extraction",
                        extra={"has_identity_info": True}
                    )
            
            if not result["recorded"] and not result["identity_updated"]:
                result["skip_reason"] = analysis.get("reason", "not_important")
            
        except Exception as e:
            logger.error(
                "Failed to analyze and record",
                extra={"error": str(e), "session_id": session_id}
            )
            result["skip_reason"] = f"error: {str(e)}"
        
        return result
    
    async def _analyze_importance(
        self,
        user_message: str,
        assistant_message: str
    ) -> dict[str, Any]:
        """Use LLM to analyze if content should be recorded."""
        try:
            prompt = MEMORY_ANALYSIS_PROMPT.format(
                user_message=user_message,
                assistant_message=assistant_message[:500] if assistant_message else ""
            )
            
            response = await self._llm_router.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )
            
            # Parse JSON response
            content = response.content.strip()
            
            # Try to extract JSON from the response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            logger.debug(
                "LLM importance analysis",
                extra={
                    "should_record": result.get("should_record"),
                    "record_type": result.get("record_type"),
                    "reason": result.get("reason", "")[:50],
                }
            )
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse LLM analysis response",
                extra={"error": str(e)}
            )
            return {"should_record": False, "reason": "parse_error"}
        except Exception as e:
            logger.error(
                "LLM analysis failed",
                extra={"error": str(e)}
            )
            return {"should_record": False, "reason": f"error: {str(e)}"}
    
    async def _extract_identity(
        self,
        user_message: str,
        assistant_message: str
    ) -> dict[str, Any]:
        """Use LLM to extract identity information."""
        try:
            prompt = IDENTITY_EXTRACTION_PROMPT.format(
                user_message=user_message,
                assistant_message=assistant_message[:500] if assistant_message else ""
            )
            
            response = await self._llm_router.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )
            
            # Parse JSON response
            content = response.content.strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse identity extraction response",
                extra={"error": str(e)}
            )
            return {"has_identity_info": False}
        except Exception as e:
            logger.error(
                "Identity extraction failed",
                extra={"error": str(e)}
            )
            return {"has_identity_info": False}
    
    def _update_identity_files(self, identity_info: dict[str, Any]) -> bool:
        """Update identity files based on extracted information."""
        updated = False
        
        try:
            # Update OWNER.md
            owner_updates = identity_info.get("owner_updates", {})
            if any(v for v in owner_updates.values() if v):
                self._update_owner_md(owner_updates)
                updated = True
            
            # Update SPIRIT.md
            spirit_updates = identity_info.get("spirit_updates", {})
            if any(v for v in spirit_updates.values() if v):
                self._update_spirit_md(spirit_updates)
                updated = True
            
            # Update IDENTITY.md
            identity_updates = identity_info.get("identity_updates", {})
            if any(v for v in identity_updates.values() if v):
                self._update_identity_md(identity_updates)
                updated = True
                
        except Exception as e:
            logger.error(
                "Failed to update identity files",
                extra={"error": str(e)}
            )
        
        return updated
    
    def _update_owner_md(self, updates: dict[str, Any]) -> None:
        """Update OWNER.md with extracted information.
        
        This method OVERWRITES existing content, not appends.
        """
        owner_path = self._workspace_path / "OWNER.md"
        
        # Ensure directory exists
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Filter out null values and DEFAULT PLACEHOLDERS
        # These are common placeholder values that should NOT be treated as real user info
        PLACEHOLDER_VALUES = {
            "用户怎么称呼", "用户姓名", "姓名", "未知", "无", "",
            "null", "None", "undefined", "-", "N/A", "n/a",
        }
        
        def is_valid_value(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, str):
                if v.strip() in PLACEHOLDER_VALUES:
                    return False
                if v.startswith("用户") or v.startswith("填入"):
                    return False
            if isinstance(v, list) and len(v) == 0:
                return False
            if isinstance(v, dict) and len(v) == 0:
                return False
            return True
        
        valid_updates = {k: v for k, v in updates.items() if is_valid_value(v)}
        
        if not valid_updates:
            logger.debug("No valid updates for OWNER.md, skipping")
            return
        
        # Build fresh content - OVERWRITE mode
        lines = [
            "# 用户画像",
            "",
            "## 基本信息",
        ]
        
        # Add name (overwrite any existing)
        if valid_updates.get("name"):
            lines.append(f"- 姓名: {valid_updates['name']}")
        else:
            lines.append("- 姓名: ")
        
        lines.append("- 年龄: ")
        
        # Add occupation (overwrite any existing)
        if valid_updates.get("occupation"):
            lines.append(f"- 职业: {valid_updates['occupation']}")
        else:
            lines.append("- 职业: ")
        
        lines.append("")
        lines.append("## 兴趣爱好")
        
        # Add interests (overwrite any existing)
        interests = valid_updates.get("interests")
        if interests and isinstance(interests, list):
            for interest in interests:
                lines.append(f"- {interest}")
        else:
            lines.append("- ")
        
        lines.append("")
        lines.append("## 当前目标")
        
        # Add goals (overwrite any existing)
        goals = valid_updates.get("goals")
        if goals and isinstance(goals, list):
            for goal in goals:
                lines.append(f"- {goal}")
        else:
            lines.append("- ")
        
        lines.append("")
        lines.append("## 偏好设置")
        
        # Add preferences (overwrite any existing)
        preferences = valid_updates.get("preferences")
        if preferences and isinstance(preferences, dict):
            for key, value in preferences.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- ")
        
        lines.append("")
        
        owner_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("OWNER.md updated (overwritten)", extra={"updates": valid_updates})
    
    def _update_spirit_md(self, updates: dict[str, Any]) -> None:
        """Update SPIRIT.md with extracted information.
        
        This method OVERWRITES existing content in each section, not appends.
        """
        spirit_path = self._workspace_path / "SPIRIT.md"
        
        # Ensure directory exists
        spirit_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Filter out null values and default placeholders
        valid_updates = {
            k: v for k, v in updates.items() 
            if v is not None and v != "null" and (not isinstance(v, list) or len(v) > 0)
            and (not isinstance(v, str) or v.strip() not in {"", "-", "N/A", "无", "未知"})
        }
        
        if not valid_updates:
            logger.debug("No valid updates for SPIRIT.md, skipping")
            return
        
        # Build fresh content - OVERWRITE mode
        sections = {
            "role": valid_updates.get("role", ""),
            "personality": valid_updates.get("personality", ""),
            "values": valid_updates.get("values", []),
            "behavior_rules": valid_updates.get("behavior_rules", []),
        }
        
        lines = [
            "# AI 人格设定",
            "",
            "## 角色定位",
        ]
        
        # Add role (overwrite any existing)
        if sections["role"]:
            lines.append(str(sections["role"]))
        lines.append("")
        
        # Add personality (overwrite any existing)
        lines.append("## 性格特征")
        if sections["personality"]:
            lines.append(str(sections["personality"]))
        lines.append("")
        
        # Add values (overwrite any existing)
        lines.append("## 价值观")
        if sections["values"]:
            for value in sections["values"]:
                lines.append(f"- {value}")
        lines.append("")
        
        # Add behavior rules (overwrite any existing)
        lines.append("## 行为准则")
        if sections["behavior_rules"]:
            for rule in sections["behavior_rules"]:
                lines.append(f"- {rule}")
        lines.append("")
        
        spirit_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("SPIRIT.md updated (overwritten)", extra={"updates": valid_updates})
    
    def _update_identity_md(self, updates: dict[str, Any]) -> None:
        """Update IDENTITY.md with extracted information."""
        identity_path = self._workspace_path / "IDENTITY.md"
        
        # Ensure directory exists
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Filter out null values and default placeholders
        valid_updates = {
            k: v for k, v in updates.items() 
            if v is not None and v != "null"
            and (not isinstance(v, str) or v.strip() not in {"", "-", "N/A", "无", "未知", "填入"})
        }
        
        if not valid_updates:
            logger.debug("No valid updates for IDENTITY.md, skipping")
            return
        
        if identity_path.exists():
            content = identity_path.read_text(encoding="utf-8")
        else:
            content = "# IDENTITY.md - Who Am I?\n\n*Fill this in during your first conversation. Make it yours.*\n\n- **Name:** \n- **Creature:** \n- **Vibe:** \n- **Emoji:** \n- **Avatar:** \n\n---\n\nThis isn't just metadata. It's the start of figuring out who you are."
        
        lines = content.split("\n")
        new_lines = []
        
        for line in lines:
            # Match format: "- **Name:** xxx" or "- **Name:**"
            if valid_updates.get("name") and "**Name:**" in line:
                line = f"- **Name:** {valid_updates['name']}"
            elif valid_updates.get("form") and "**Creature:**" in line:
                line = f"- **Creature:** {valid_updates['form']}"
            elif valid_updates.get("style") and "**Vibe:**" in line:
                line = f"- **Vibe:** {valid_updates['style']}"
            elif valid_updates.get("emoji") and "**Emoji:**" in line:
                line = f"- **Emoji:** {valid_updates['emoji']}"
            
            new_lines.append(line)
        
        identity_path.write_text("\n".join(new_lines), encoding="utf-8")
        logger.info("IDENTITY.md updated", extra={"updates": valid_updates})
    
    def _update_long_term_memory(self, content: str, reason: str = "") -> None:
        """Update MEMORY.md with important content in real-time.
        
        This method appends important content to MEMORY.md immediately,
        rather than waiting for the scheduled maintenance task.
        
        Args:
            content: The extracted important content
            reason: The reason why this content was deemed important
        """
        memory_path = self._workspace_path / "MEMORY.md"
        
        # Ensure directory exists
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read existing content
        if memory_path.exists():
            existing_content = memory_path.read_text(encoding="utf-8")
        else:
            existing_content = """# 长期记忆

此文件存储经过提炼的持久化记忆摘要，跨日期的重要信息。

## 格式说明
每个记忆条目应包含：
- 时间戳
- 关键内容摘要
- 相关上下文标签

---

## 记忆条目

"""
        
        # Check for duplicate - don't add if already exists
        if content in existing_content:
            logger.debug("Content already exists in MEMORY.md, skipping")
            return
        
        # Determine category based on reason
        category = "重要记录"
        if "偏好" in reason or "喜欢" in reason:
            category = "用户偏好"
        elif "决策" in reason:
            category = "重要决策"
        elif "身份" in reason or "姓名" in reason:
            category = "身份信息"
        elif "约定" in reason or "计划" in reason:
            category = "重要约定"
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        # Append new entry
        new_entry = f"\n### {timestamp}\n[{category}] {content}\n"
        
        # Find the insertion point (after "## 记忆条目")
        lines = existing_content.split("\n")
        insert_index = -1
        
        for i, line in enumerate(lines):
            if line.strip() == "## 记忆条目":
                insert_index = i + 1
                # Skip empty lines after header
                while insert_index < len(lines) and lines[insert_index].strip() == "":
                    insert_index += 1
                break
        
        if insert_index >= 0:
            lines.insert(insert_index, new_entry.strip())
        else:
            # Fallback: append to end
            lines.append(new_entry)
        
        memory_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "MEMORY.md updated in real-time",
            extra={"content": content[:50], "category": category}
        )


# Global service instance
_smart_memory_service: "SmartMemoryService | None" = None


def get_smart_memory_service(
    llm_router: "LLMRouter | None" = None,
    workspace_path: str = "workspace"
) -> "SmartMemoryService":
    """Get or create global smart memory service instance.
    
    Args:
        llm_router: LLM router instance
        workspace_path: Path to workspace
        
    Returns:
        SmartMemoryService instance
    """
    global _smart_memory_service
    if _smart_memory_service is None:
        if llm_router is None:
            from ..services.llm.router import LLMRouter
            from ..config.manager import ConfigManager
            config = ConfigManager().config
            llm_router = LLMRouter(config.models)
        _smart_memory_service = SmartMemoryService(llm_router, workspace_path)
    return _smart_memory_service
