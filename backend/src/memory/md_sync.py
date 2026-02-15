"""Markdown file synchronization for memory system.

This module provides:
- Frontmatter parsing and generation
- Markdown file reading and writing
- Bidirectional sync between .md files and memory structures
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from .models import (
    DailyLog,
    MemoryContentType,
    MemoryEntry,
    OwnerProfile,
    SpiritConfig,
    ToolDefinition,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MarkdownSync:
    """Synchronization between Markdown files and memory structures.
    
    Handles reading and writing of:
    - SPIRIT.md: AI personality configuration
    - OWNER.md: User profile
    - TOOLS.md: Tool definitions
    - memory/*.md: Daily memory logs
    """
    
    def __init__(self, workspace_path: str) -> None:
        """Initialize markdown sync.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self.spirit_path = self.workspace_path / "SPIRIT.md"
        self.owner_path = self.workspace_path / "OWNER.md"
        self.tools_path = self.workspace_path / "TOOLS.md"
        self.memory_path = self.workspace_path / "memory"
        
        logger.info(
            "MarkdownSync initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    # ============ Spirit (AI Personality) ============
    
    def load_spirit(self) -> SpiritConfig | None:
        """Load AI personality from SPIRIT.md.
        
        Returns:
            SpiritConfig if file exists, None otherwise
        """
        if not self.spirit_path.exists():
            logger.debug("SPIRIT.md does not exist")
            return None
        
        try:
            with open(self.spirit_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Parse frontmatter if present
            try:
                post = frontmatter.loads(content)
                data = post.metadata
                content_body = post.content
            except Exception:
                data = {}
                content_body = content
            
            # Parse content sections
            config = self._parse_spirit_content(content_body)
            
            # Override with frontmatter data if present
            if data:
                config.role = data.get("role", config.role)
                config.personality = data.get("personality", config.personality)
                if "values" in data:
                    config.values = data["values"]
                if "behavior_rules" in data:
                    config.behavior_rules = data["behavior_rules"]
            
            config.file_path = str(self.spirit_path)
            config.last_modified = datetime.fromtimestamp(
                self.spirit_path.stat().st_mtime
            )
            
            logger.info(
                "SPIRIT.md loaded",
                extra={
                    "role": config.role[:50] if config.role else "",
                    "values_count": len(config.values),
                }
            )
            return config
            
        except Exception as e:
            logger.error(
                "Failed to load SPIRIT.md",
                extra={"error": str(e)}
            )
            return None
    
    def _parse_spirit_content(self, content: str) -> SpiritConfig:
        """Parse SPIRIT.md content sections."""
        config = SpiritConfig()
        
        # Extract sections
        sections = self._extract_sections(content)
        
        if "角色定位" in sections:
            config.role = sections["角色定位"].strip()
        if "性格特征" in sections:
            config.personality = sections["性格特征"].strip()
        if "价值观" in sections:
            config.values = self._parse_list_items(sections["价值观"])
        if "行为准则" in sections:
            config.behavior_rules = self._parse_list_items(sections["行为准则"])
        
        return config
    
    def save_spirit(self, config: SpiritConfig) -> bool:
        """Save AI personality to SPIRIT.md.
        
        Args:
            config: Spirit configuration to save
            
        Returns:
            True if saved successfully
        """
        try:
            content = f"""# AI 人格设定

## 角色定位
{config.role}

## 性格特征
{config.personality}

## 价值观
{self._format_list_items(config.values)}

## 行为准则
{self._format_list_items(config.behavior_rules)}
"""
            
            # Ensure workspace exists
            self.workspace_path.mkdir(parents=True, exist_ok=True)
            
            with open(self.spirit_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(
                "SPIRIT.md saved",
                extra={"role": config.role[:50] if config.role else ""}
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to save SPIRIT.md",
                extra={"error": str(e)}
            )
            return False
    
    # ============ Owner (User Profile) ============
    
    def load_owner(self) -> OwnerProfile | None:
        """Load user profile from OWNER.md.
        
        Returns:
            OwnerProfile if file exists, None otherwise
        """
        if not self.owner_path.exists():
            logger.debug("OWNER.md does not exist")
            return None
        
        try:
            with open(self.owner_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            config = self._parse_owner_content(content)
            config.file_path = str(self.owner_path)
            config.last_modified = datetime.fromtimestamp(
                self.owner_path.stat().st_mtime
            )
            
            logger.info(
                "OWNER.md loaded",
                extra={"name": config.name}
            )
            return config
            
        except Exception as e:
            logger.error(
                "Failed to load OWNER.md",
                extra={"error": str(e)}
            )
            return None
    
    def _parse_owner_content(self, content: str) -> OwnerProfile:
        """Parse OWNER.md content sections."""
        config = OwnerProfile()
        sections = self._extract_sections(content)
        
        if "基本信息" in sections:
            info = sections["基本信息"]
            # Parse name
            name_match = re.search(r"姓名[：:]\s*(.+)", info)
            if name_match:
                config.name = name_match.group(1).strip()
            # Parse age
            age_match = re.search(r"年龄[：:]\s*(\d+)", info)
            if age_match:
                config.age = int(age_match.group(1))
            # Parse occupation
            occ_match = re.search(r"职业[：:]\s*(.+)", info)
            if occ_match:
                config.occupation = occ_match.group(1).strip()
        
        if "兴趣爱好" in sections:
            config.interests = self._parse_list_items(sections["兴趣爱好"])
        if "当前目标" in sections:
            config.goals = self._parse_list_items(sections["当前目标"])
        if "偏好设置" in sections:
            config.preferences = self._parse_key_value_items(sections["偏好设置"])
        
        return config
    
    def save_owner(self, config: OwnerProfile) -> bool:
        """Save user profile to OWNER.md.
        
        Args:
            config: Owner profile to save
            
        Returns:
            True if saved successfully
        """
        try:
            age_str = str(config.age) if config.age else ""
            content = f"""# 用户画像

## 基本信息
- 姓名: {config.name}
- 年龄: {age_str}
- 职业: {config.occupation}

## 兴趣爱好
{self._format_list_items(config.interests)}

## 当前目标
{self._format_list_items(config.goals)}

## 偏好设置
{self._format_key_value_items(config.preferences)}
"""
            
            self.workspace_path.mkdir(parents=True, exist_ok=True)
            
            with open(self.owner_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(
                "OWNER.md saved",
                extra={"name": config.name}
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to save OWNER.md",
                extra={"error": str(e)}
            )
            return False
    
    # ============ Tools ============
    
    def load_tools(self) -> list[ToolDefinition]:
        """Load tool definitions from TOOLS.md.
        
        Returns:
            List of tool definitions
        """
        if not self.tools_path.exists():
            logger.debug("TOOLS.md does not exist")
            return []
        
        try:
            with open(self.tools_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tools = self._parse_tools_content(content)
            
            logger.info(
                "TOOLS.md loaded",
                extra={"tools_count": len(tools)}
            )
            return tools
            
        except Exception as e:
            logger.error(
                "Failed to load TOOLS.md",
                extra={"error": str(e)}
            )
            return []
    
    def _parse_tools_content(self, content: str) -> list[ToolDefinition]:
        """Parse TOOLS.md content."""
        tools: list[ToolDefinition] = []
        
        # Simple parsing: look for tool names in backticks
        for match in re.finditer(r"`(\w+)`:\s*(.+)", content):
            tools.append(ToolDefinition(
                name=match.group(1),
                description=match.group(2).strip(),
            ))
        
        return tools
    
    # ============ Memory Entries ============
    
    def load_daily_log(self, date: str) -> DailyLog | None:
        """Load daily log for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD)
            
        Returns:
            DailyLog if file exists, None otherwise
        """
        file_path = self.memory_path / f"{date}.md"
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            log = DailyLog(
                date=date,
                file_path=str(file_path),
            )
            
            # Parse entries from content
            # Entry format: ### HH:MM - [type]\ncontent
            for match in re.finditer(
                r"###\s*(\d{2}:\d{2})\s*-\s*(\w+)\s*\n(.+?)(?=###|$)",
                content,
                re.DOTALL
            ):
                log.entries.append(f"{date}-{match.group(1)}")
            
            return log
            
        except Exception as e:
            logger.error(
                "Failed to load daily log",
                extra={"date": date, "error": str(e)}
            )
            return None
    
    def append_memory_entry(self, entry: MemoryEntry) -> bool:
        """Append a memory entry to the daily log.
        
        Args:
            entry: Memory entry to append
            
        Returns:
            True if appended successfully
        """
        import uuid
        
        date_str = entry.created_at.strftime("%Y-%m-%d")
        # Use seconds in timestamp for uniqueness
        time_str = entry.created_at.strftime("%H:%M:%S")
        file_path = self.memory_path / f"{date_str}.md"
        
        # Generate unique ID if not provided
        # Format: date-time-uuid8 (e.g., 2026-02-14-20:38:45-a3b4c5d6)
        if not entry.id or entry.id.startswith("tmp-"):
            entry.id = f"{date_str}-{time_str}-{uuid.uuid4().hex[:8]}"
        
        try:
            # Ensure memory directory exists
            self.memory_path.mkdir(parents=True, exist_ok=True)
            
            # Create file with header if it doesn't exist
            if not file_path.exists():
                header = f"# {date_str} 日志\n\n## 摘要\n\n## 记录条目\n\n"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(header)
            
            # Append entry with full timestamp
            entry_text = f"\n### {time_str} - {entry.content_type}\n{entry.content}\n"
            
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry_text)
            
            logger.info(
                "Memory entry appended",
                extra={
                    "entry_id": entry.id,
                    "date": date_str,
                    "content_type": entry.content_type,
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to append memory entry",
                extra={"entry_id": entry.id, "error": str(e)}
            )
            return False
    
    # ============ Helper Methods ============
    
    def _extract_sections(self, content: str) -> dict[str, str]:
        """Extract sections from markdown content.
        
        Sections are identified by ## headers.
        """
        sections: dict[str, str] = {}
        current_section = ""
        current_content: list[str] = []
        
        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = "\n".join(current_content)
        
        return sections
    
    def _parse_list_items(self, content: str) -> list[str]:
        """Parse list items from content."""
        items: list[str] = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
        return items
    
    def _format_list_items(self, items: list[str]) -> str:
        """Format list items as markdown."""
        if not items:
            return "- "
        return "\n".join(f"- {item}" for item in items)
    
    def _parse_key_value_items(self, content: str) -> dict[str, str]:
        """Parse key-value items from content."""
        result: dict[str, str] = {}
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]
            if "：" in line:
                key, value = line.split("：", 1)
                result[key.strip()] = value.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result
    
    def _format_key_value_items(self, items: dict[str, str]) -> str:
        """Format key-value items as markdown."""
        if not items:
            return "- "
        return "\n".join(f"- {k}: {v}" for k, v in items.items())
    
    # ============ Identity Status ============
    
    def check_identity_status(self) -> dict[str, bool]:
        """Check if identity files exist.
        
        Returns:
            Dictionary with status of each identity file
        """
        return {
            "has_spirit": self.spirit_path.exists(),
            "has_owner": self.owner_path.exists(),
            "initialized": self.spirit_path.exists() and self.owner_path.exists(),
        }
    
    # ============ Entry Management ============
    
    def load_entries_from_log(self, date: str) -> list[MemoryEntry]:
        """Load all entries from a daily log file.
        
        Args:
            date: Date string (YYYY-MM-DD)
            
        Returns:
            List of MemoryEntry objects
        """
        file_path = self.memory_path / f"{date}.md"
        entries: list[MemoryEntry] = []
        
        if not file_path.exists():
            return entries
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Parse entries: ### HH:MM - [type]\ncontent
            # Also support new format with sequence: ### HH:MM:SS - [type]\ncontent
            pattern = r"###\s*(\d{2}:\d{2}(?::\d{2})?)\s*-\s*(\w+)\s*\n(.+?)(?=###|$)"
            
            # Track time occurrences to generate unique IDs
            time_counter: dict[str, int] = {}
            
            for match in re.finditer(pattern, content, re.DOTALL):
                time_str = match.group(1)
                content_type_str = match.group(2).lower()
                entry_content = match.group(3).strip()
                
                # Create datetime from date and time
                try:
                    if len(time_str) == 5:  # HH:MM format
                        created_at = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
                    else:  # HH:MM:SS format
                        created_at = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_at = datetime.now()
                
                # Generate unique ID with sequence number
                time_key = f"{date}-{time_str}"
                seq = time_counter.get(time_key, 0) + 1
                time_counter[time_key] = seq
                
                # ID format: date-time-seq (e.g., 2026-02-14-20:38-1)
                entry_id = f"{time_key}-{seq}"
                
                # Map content type
                content_type = MemoryContentType.CONVERSATION
                if content_type_str == "decision":
                    content_type = MemoryContentType.DECISION
                elif content_type_str == "summary":
                    content_type = MemoryContentType.SUMMARY
                elif content_type_str == "manual":
                    content_type = MemoryContentType.MANUAL
                
                entry = MemoryEntry(
                    id=entry_id,
                    content=entry_content,
                    content_type=content_type,
                    source_file=str(file_path),
                    created_at=created_at,
                )
                entries.append(entry)
            
            return entries
            
        except Exception as e:
            logger.error(
                "Failed to load entries from log",
                extra={"date": date, "error": str(e)}
            )
            return entries
    
    def list_all_entries(
        self,
        limit: int = 20,
        offset: int = 0,
        content_type: str | None = None,
    ) -> list[MemoryEntry]:
        """List all memory entries across all daily logs.
        
        Args:
            limit: Maximum number of entries
            offset: Pagination offset
            content_type: Optional filter by content type
            
        Returns:
            List of MemoryEntry objects
        """
        all_entries: list[MemoryEntry] = []
        
        if not self.memory_path.exists():
            return all_entries
        
        # Get all log files sorted by date (newest first)
        log_files = sorted(
            self.memory_path.glob("*.md"),
            key=lambda p: p.stem,
            reverse=True
        )
        
        for log_file in log_files:
            date = log_file.stem
            entries = self.load_entries_from_log(date)
            
            # Filter by content type if specified
            if content_type:
                entries = [e for e in entries if e.content_type == content_type]
            
            all_entries.extend(entries)
            
            # Stop if we have enough entries
            if len(all_entries) >= limit + offset:
                break
        
        # Apply pagination
        return all_entries[offset:offset + limit]
    
    def get_entry_by_id(self, entry_id: str) -> MemoryEntry | None:
        """Get a specific memory entry by ID.
        
        Args:
            entry_id: Entry ID (format: YYYY-MM-DD-HH:MM or UUID)
            
        Returns:
            MemoryEntry if found, None otherwise
        """
        # Parse date from entry_id
        if "-" in entry_id and len(entry_id) >= 10:
            # Try to extract date from ID
            parts = entry_id.split("-")
            if len(parts) >= 3:
                date = "-".join(parts[:3])
                entries = self.load_entries_from_log(date)
                for entry in entries:
                    if entry.id == entry_id:
                        return entry
        
        return None
    
    def delete_entry(self, entry_id: str) -> bool:
        """Delete a memory entry from daily log.
        
        Args:
            entry_id: Entry ID to delete
            
        Returns:
            True if deleted successfully
        """
        entry = self.get_entry_by_id(entry_id)
        if entry is None:
            return False
        
        date = entry.created_at.strftime("%Y-%m-%d")
        time_str = entry.created_at.strftime("%H:%M")
        file_path = self.memory_path / f"{date}.md"
        
        if not file_path.exists():
            return False
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Remove the entry section
            pattern = rf"\n###\s*{time_str}\s*-\s*\w+\s*\n.+?(?=###|$)"
            new_content = re.sub(pattern, "", content, flags=re.DOTALL)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            logger.info(
                "Memory entry deleted",
                extra={"entry_id": entry_id, "date": date}
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to delete memory entry",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            return False
    
    def list_available_dates(self) -> list[str]:
        """List all dates that have daily logs.
        
        Returns:
            List of date strings (YYYY-MM-DD)
        """
        if not self.memory_path.exists():
            return []
        
        dates: list[str] = []
        for log_file in self.memory_path.glob("*.md"):
            # Check if filename is a valid date
            date_str = log_file.stem
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                dates.append(date_str)
            except ValueError:
                continue
        
        return sorted(dates, reverse=True)

    # ============ Bidirectional Sync (Phase 7) ============

    def sync_entry_to_vector_store(
        self,
        entry: MemoryEntry,
        vector_store: Any,
        embedder: Any,
    ) -> bool:
        """Sync a memory entry to vector store.
        
        Args:
            entry: Memory entry to sync
            vector_store: VectorStore instance
            embedder: Embedder instance
            
        Returns:
            True if sync successful
        """
        try:
            # Generate embedding
            embedding = embedder.embed(entry.content)
            
            # Get content type string
            content_type = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
            
            # Insert into vector store
            vector_store.insert(
                entry_id=entry.id,
                embedding=embedding,
                content=entry.content,
                content_type=content_type,
                metadata={
                    "source_file": entry.source_file,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                }
            )
            
            logger.info(
                "Entry synced to vector store",
                extra={"entry_id": entry.id, "content_type": content_type}
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to sync entry to vector store",
                extra={"entry_id": entry.id, "error": str(e)}
            )
            return False

    def sync_all_entries_to_vector_store(
        self,
        vector_store: Any,
        embedder: Any,
        limit: int = 1000,
    ) -> int:
        """Sync all markdown entries to vector store.
        
        Useful for initial sync on startup.
        
        Args:
            vector_store: VectorStore instance
            embedder: Embedder instance
            limit: Maximum entries to sync
            
        Returns:
            Number of entries synced
        """
        entries = self.list_all_entries(limit=limit)
        synced = 0
        
        for entry in entries:
            if self.sync_entry_to_vector_store(entry, vector_store, embedder):
                synced += 1
        
        logger.info(
            "Bulk sync completed",
            extra={"total_entries": len(entries), "synced": synced}
        )
        
        return synced

    def delete_entry_from_vector_store(
        self,
        entry_id: str,
        vector_store: Any,
    ) -> bool:
        """Delete an entry from vector store.
        
        Args:
            entry_id: Entry ID to delete
            vector_store: VectorStore instance
            
        Returns:
            True if deletion successful
        """
        try:
            deleted = vector_store.delete(entry_id)
            
            if deleted:
                logger.info(
                    "Entry deleted from vector store",
                    extra={"entry_id": entry_id}
                )
            return deleted
            
        except Exception as e:
            logger.error(
                "Failed to delete entry from vector store",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            return False

    def recover_entries_from_vector_store(
        self,
        vector_store: Any,
        limit: int = 1000,
    ) -> int:
        """Recover entries from vector store to Markdown files.
        
        Used when Markdown files are corrupted or missing.
        
        Args:
            vector_store: VectorStore instance
            limit: Maximum entries to recover
            
        Returns:
            Number of entries recovered
        """
        try:
            entries_data = vector_store.get_all_entries(limit=limit)
            recovered = 0
            
            for entry_data in entries_data:
                # Check if already exists in markdown
                existing = self.get_entry_by_id(entry_data["id"])
                if existing:
                    continue
                
                # Create entry from vector store data
                content_type_str = entry_data.get("content_type", "conversation")
                try:
                    content_type = MemoryContentType(content_type_str)
                except ValueError:
                    content_type = MemoryContentType.CONVERSATION
                
                entry = MemoryEntry(
                    id=entry_data["id"],
                    content=entry_data["content"],
                    content_type=content_type,
                    source_file=entry_data.get("source_file", ""),
                    metadata=entry_data.get("metadata", {}),
                )
                
                # Append to markdown
                if self.append_memory_entry(entry):
                    recovered += 1
            
            logger.info(
                "Recovery from vector store completed",
                extra={"recovered": recovered, "total": len(entries_data)}
            )
            
            return recovered
            
        except Exception as e:
            logger.error(
                "Failed to recover entries from vector store",
                extra={"error": str(e)}
            )
            return 0

    def sync_on_file_change(
        self,
        file_path: str,
        vector_store: Any,
        embedder: Any,
    ) -> bool:
        """Handle file change event and sync to vector store.
        
        Called by file watcher when a memory file changes.
        
        Args:
            file_path: Path to changed file
            vector_store: VectorStore instance
            embedder: Embedder instance
            
        Returns:
            True if sync successful
        """
        try:
            path = Path(file_path)
            
            # Only process memory log files
            if path.parent.name != "memory" or path.suffix != ".md":
                return False
            
            # Load entries from the file
            date_str = path.stem
            entries = self.load_entries_from_log(date_str)
            
            # Sync each entry
            for entry in entries:
                self.sync_entry_to_vector_store(entry, vector_store, embedder)
            
            logger.info(
                "File change synced to vector store",
                extra={"file_path": file_path, "entries_count": len(entries)}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to sync file change",
                extra={"file_path": file_path, "error": str(e)}
            )
            return False


# Global markdown sync instance
_md_sync: MarkdownSync | None = None


def get_md_sync(workspace_path: str | None = None) -> MarkdownSync:
    """Get or create global markdown sync instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        MarkdownSync instance
    """
    global _md_sync
    if _md_sync is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _md_sync = MarkdownSync(workspace_path)
    return _md_sync
