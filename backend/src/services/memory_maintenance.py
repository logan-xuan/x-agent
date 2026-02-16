"""Memory maintenance service for daily log processing and MEMORY.md updates.

This module provides:
- Importance scoring for memory entries (T040)
- Daily memory parsing (T041)
- MEMORY.md update logic (T042)
- Scheduled task with APScheduler (T043)
- File lock for concurrent write safety (T044)
"""

import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles
import filelock

from ..memory.models import MemoryEntry, MemoryContentType
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MemoryMaintenanceService:
    """Service for maintaining and updating memory files.
    
    Handles:
    - Processing daily logs to extract important content
    - Updating MEMORY.md with consolidated memories
    - Cleaning up old/outdated entries
    - Scheduled maintenance tasks
    """
    
    # Keywords that indicate important content
    IMPORTANCE_KEYWORDS = [
        "重要", "关键", "决策", "偏好", "选择", "确定",
        "决定", "结论", "注意", "目标", "计划",
    ]
    
    # Content type base scores
    CONTENT_TYPE_SCORES = {
        MemoryContentType.DECISION: 4,  # Decisions are important
        MemoryContentType.MANUAL: 4,    # Manual entries are curated
        MemoryContentType.SUMMARY: 3,   # Summaries are moderately important
        MemoryContentType.CONVERSATION: 2,  # Conversations need filtering
    }
    
    def __init__(
        self,
        workspace_path: str,
        llm_client: Any = None,
        min_importance: int = 4,
        keep_days: int = 30,
    ) -> None:
        """Initialize memory maintenance service.
        
        Args:
            workspace_path: Path to workspace directory
            llm_client: Optional LLM client for intelligent analysis
            min_importance: Minimum importance score to include in MEMORY.md
            keep_days: Number of days to keep daily logs
        """
        self.workspace_path = Path(workspace_path)
        self.memory_path = self.workspace_path / "memory"
        self.memory_md_path = self.workspace_path / "MEMORY.md"
        self.llm_client = llm_client
        self.min_importance = min_importance
        self.keep_days = keep_days
        
        # File lock for concurrent access
        self._lock = filelock.FileLock(str(self.workspace_path / ".memory.lock"))
        
        logger.info(
            "MemoryMaintenanceService initialized",
            extra={
                "workspace_path": str(self.workspace_path),
                "min_importance": min_importance,
            }
        )
    
    def calculate_importance_score(self, entry: MemoryEntry) -> int:
        """Calculate importance score for a memory entry.
        
        T040: Implements importance scoring based on:
        - Content type (base score)
        - Keyword presence (boost)
        - Content length (penalty for very short entries)
        
        Args:
            entry: Memory entry to score
            
        Returns:
            Importance score (1-5)
        """
        # Get base score from content type
        base_score = self.CONTENT_TYPE_SCORES.get(
            entry.content_type, 
            MemoryContentType.CONVERSATION
        )
        
        score = base_score
        
        # Boost for important keywords
        content_lower = entry.content.lower()
        keyword_matches = sum(1 for kw in self.IMPORTANCE_KEYWORDS if kw in content_lower)
        score += min(keyword_matches, 2)  # Max +2 from keywords
        
        # Penalty for very short content (likely not important)
        if len(entry.content) < 10:
            score -= 1
        
        # Cap score between 1 and 5
        return max(1, min(5, score))
    
    async def analyze_importance_with_llm(self, entry: MemoryEntry) -> dict[str, Any]:
        """Analyze entry importance using LLM.
        
        Uses LLM for intelligent content analysis when available.
        
        Args:
            entry: Memory entry to analyze
            
        Returns:
            Dict with importance, category, and summary
        """
        if not self.llm_client:
            # Fallback to rule-based scoring
            return {
                "importance": self.calculate_importance_score(entry),
                "category": entry.content_type.value,
                "summary": entry.content[:100],
            }
        
        try:
            # Handle both enum and string content_type
            content_type_str = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
            
            prompt = f"""分析以下记忆内容，返回JSON格式的分析结果：
内容: {entry.content}
类型: {content_type_str}

请返回JSON:
{{"importance": 1-5, "category": "决策/偏好/经验/其他", "summary": "摘要"}}"""

            response = await self.llm_client.chat([{"role": "user", "content": prompt}])
            
            # Parse JSON response
            import json
            # Extract JSON from response
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            
            logger.debug(
                "LLM importance analysis completed",
                extra={"entry_id": entry.id, "result": result}
            )
            
            return result
            
        except Exception as e:
            logger.warning(
                "LLM analysis failed, using fallback",
                extra={"entry_id": entry.id, "error": str(e)}
            )
            # Handle both enum and string content_type
            content_type_str = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
            return {
                "importance": self.calculate_importance_score(entry),
                "category": content_type_str,
                "summary": entry.content[:100],
            }
    
    def filter_important_entries(
        self,
        entries: list[MemoryEntry],
        min_importance: int | None = None,
    ) -> list[MemoryEntry]:
        """Filter entries by importance threshold.
        
        Args:
            entries: List of memory entries
            min_importance: Minimum importance score (uses service default if not provided)
            
        Returns:
            Filtered list of important entries
        """
        threshold = min_importance or self.min_importance
        
        important = []
        for entry in entries:
            score = self.calculate_importance_score(entry)
            if score >= threshold:
                important.append(entry)
                logger.debug(
                    "Entry passed importance filter",
                    extra={"entry_id": entry.id, "score": score}
                )
        
        return important
    
    def ensure_memory_md_exists(self) -> None:
        """Create MEMORY.md with template if it doesn't exist.
        
        T042: Ensures MEMORY.md exists before operations.
        """
        if self.memory_md_path.exists():
            return
        
        template = """# 长期记忆

此文件存储经过提炼的持久化记忆摘要，跨日期的重要信息。

## 格式说明
每个记忆条目应包含：
- 时间戳
- 关键内容摘要
- 相关上下文标签

---

## 记忆条目

### 决策
<!-- 重要决策记录 -->

### 偏好
<!-- 用户偏好记录 -->

### 经验
<!-- 经验教训记录 -->

"""
        
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.memory_md_path.write_text(template)
        
        logger.info("MEMORY.md created with template")
    
    def parse_daily_log(self, date: str) -> list[MemoryEntry]:
        """Parse a daily log file into memory entries.
        
        T041: Parses memory/YYYY-MM-DD.md files.
        
        Args:
            date: Date string (YYYY-MM-DD)
            
        Returns:
            List of MemoryEntry objects
        """
        file_path = self.memory_path / f"{date}.md"
        
        if not file_path.exists():
            return []
        
        try:
            content = file_path.read_text(encoding="utf-8")
            entries: list[MemoryEntry] = []
            
            # Parse entries: ### HH:MM(:SS) - [type]\ncontent
            pattern = r"###\s*(\d{2}:\d{2}(?::\d{2})?)\s*-\s*(\w+)\s*\n(.+?)(?=###|$)"
            
            time_counter: dict[str, int] = {}
            
            for match in re.finditer(pattern, content, re.DOTALL):
                time_str = match.group(1)
                content_type_str = match.group(2).lower()
                entry_content = match.group(3).strip()
                
                # Skip merged entries
                if "[merged]" in entry_content.lower():
                    continue
                
                # Create datetime
                try:
                    if len(time_str) == 5:
                        created_at = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
                    else:
                        created_at = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_at = datetime.now()
                
                # Generate unique ID
                time_key = f"{date}-{time_str}"
                seq = time_counter.get(time_key, 0) + 1
                time_counter[time_key] = seq
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
                "Failed to parse daily log",
                extra={"date": date, "error": str(e)}
            )
            return []
    
    def get_existing_memory_entries(self) -> dict[str, list[str]]:
        """Get existing entries from MEMORY.md by category.
        
        Returns:
            Dict mapping category to list of existing entries
        """
        if not self.memory_md_path.exists():
            return {}
        
        content = self.memory_md_path.read_text(encoding="utf-8")
        
        result: dict[str, list[str]] = {
            "决策": [],
            "偏好": [],
            "经验": [],
        }
        
        # Extract entries by section
        current_section = None
        for line in content.split("\n"):
            if line.startswith("### "):
                current_section = line[4:].strip()
                if current_section not in result:
                    result[current_section] = []
            elif line.startswith("- [") and current_section:
                result[current_section].append(line)
        
        return result
    
    def append_to_memory_md(self, entries: list[dict[str, Any]]) -> int:
        """Append new entries to MEMORY.md.
        
        T042: Updates MEMORY.md with new important entries.
        
        Args:
            entries: List of entry dicts with content, category, date
            
        Returns:
            Number of entries added
        """
        if not entries:
            return 0
        
        self.ensure_memory_md_exists()
        
        with self._lock:
            content = self.memory_md_path.read_text(encoding="utf-8")
            
            # Get existing entries to avoid duplicates
            existing = set()
            for line in content.split("\n"):
                if line.startswith("- ["):
                    # Extract content for comparison
                    existing.add(line.lower())
            
            added = 0
            new_lines: dict[str, list[str]] = {
                "决策": [],
                "偏好": [],
                "经验": [],
            }
            
            for entry in entries:
                category = entry.get("category", "经验")
                if category not in new_lines:
                    category = "经验"
                
                date = entry.get("date", datetime.now().strftime("%Y-%m-%d"))
                entry_content = entry.get("content", "")
                
                # Create entry line
                line = f"- [{date}] {entry_content}"
                
                # Check for duplicates
                if line.lower() not in existing:
                    new_lines[category].append(line)
                    existing.add(line.lower())
                    added += 1
            
            if added == 0:
                return 0
            
            # Insert new entries into appropriate sections
            lines = content.split("\n")
            updated_lines: list[str] = []
            current_section = None
            
            for line in lines:
                updated_lines.append(line)
                
                if line.startswith("### "):
                    current_section = line[4:].strip()
                    
                    # Add new entries after section header
                    if current_section in new_lines and new_lines[current_section]:
                        for new_entry in new_lines[current_section]:
                            updated_lines.append(new_entry)
                        new_lines[current_section] = []  # Clear to avoid re-adding
            
            # Write updated content
            self.memory_md_path.write_text("\n".join(updated_lines), encoding="utf-8")
            
            logger.info(
                "MEMORY.md updated",
                extra={"entries_added": added}
            )
            
            return added
    
    def process_daily_logs_to_memory_md(
        self,
        min_importance: int | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Process daily logs and update MEMORY.md.
        
        T042: Main method for processing daily logs to MEMORY.md.
        
        Args:
            min_importance: Minimum importance threshold
            days: Number of recent days to process
            
        Returns:
            Dict with processing results
        """
        self.ensure_memory_md_exists()
        
        threshold = min_importance or self.min_importance
        processed = 0
        entries_to_add: list[dict[str, Any]] = []
        
        # Process recent daily logs
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            entries = self.parse_daily_log(date)
            
            for entry in entries:
                score = self.calculate_importance_score(entry)
                
                if score >= threshold:
                    entries_to_add.append({
                        "content": entry.content,
                        "category": self._map_content_type_to_category(entry.content_type),
                        "date": entry.created_at.strftime("%Y-%m-%d"),
                        "importance": score,
                    })
                    processed += 1
        
        # Append to MEMORY.md
        added = self.append_to_memory_md(entries_to_add)
        
        return {
            "processed": processed,
            "added": added,
            "threshold": threshold,
        }
    
    def _map_content_type_to_category(self, content_type: MemoryContentType) -> str:
        """Map content type to MEMORY.md category."""
        mapping = {
            MemoryContentType.DECISION: "决策",
            MemoryContentType.MANUAL: "偏好",
            MemoryContentType.SUMMARY: "经验",
            MemoryContentType.CONVERSATION: "经验",
        }
        return mapping.get(content_type, "经验")
    
    def cleanup_old_daily_logs(self, keep_days: int | None = None) -> dict[str, Any]:
        """Clean up old daily log files.
        
        T039: Removes daily logs older than keep_days.
        
        Args:
            keep_days: Number of days to keep (uses service default if not provided)
            
        Returns:
            Dict with cleanup results
        """
        days = keep_days or self.keep_days
        cutoff_date = datetime.now() - timedelta(days=days)
        removed = 0
        
        if not self.memory_path.exists():
            return {"removed": 0, "kept": 0}
        
        kept = 0
        for log_file in self.memory_path.glob("*.md"):
            # Skip archive directory
            if log_file.parent.name == "archive":
                continue
            
            date_str = log_file.stem
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    removed += 1
                    logger.info(
                        "Old daily log removed",
                        extra={"file": str(log_file)}
                    )
                else:
                    kept += 1
            except ValueError:
                # Not a date-formatted file, skip
                continue
        
        return {"removed": removed, "kept": kept}
    
    def mark_entries_as_merged(self, entry_ids: list[str]) -> int:
        """Mark entries as merged in daily logs.
        
        T039: Marks entries that have been merged to MEMORY.md.
        
        Args:
            entry_ids: List of entry IDs to mark
            
        Returns:
            Number of entries marked
        """
        marked = 0
        
        # Group by date
        by_date: dict[str, list[str]] = {}
        for entry_id in entry_ids:
            parts = entry_id.split("-")
            if len(parts) >= 3:
                date = "-".join(parts[:3])
                if date not in by_date:
                    by_date[date] = []
                by_date[date].append(entry_id)
        
        for date, ids in by_date.items():
            file_path = self.memory_path / f"{date}.md"
            
            if not file_path.exists():
                continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                
                for entry_id in ids:
                    # Find and mark the entry
                    # Entry ID format: date-time-seq
                    time_part = "-".join(entry_id.split("-")[3:5])
                    pattern = rf"(###\s*{time_part}\s*-\s*\w+\s*\n)(.+?)(?=###|$)"
                    
                    def add_merged_marker(match):
                        return f"{match.group(1)}[merged] {match.group(2)}"
                    
                    new_content = re.sub(pattern, add_merged_marker, content, flags=re.DOTALL)
                    content = new_content
                    marked += 1
                
                file_path.write_text(content, encoding="utf-8")
                
            except Exception as e:
                logger.error(
                    "Failed to mark entries as merged",
                    extra={"date": date, "error": str(e)}
                )
        
        return marked
    
    def archive_old_memory_entries(self, keep_days: int | None = None) -> dict[str, Any]:
        """Archive old entries from MEMORY.md.
        
        T039: Moves old entries to archive.
        
        Args:
            keep_days: Number of days to keep entries
            
        Returns:
            Dict with archive results
        """
        days = keep_days or self.keep_days
        cutoff_date = datetime.now() - timedelta(days=days)
        archived = 0
        
        if not self.memory_md_path.exists():
            return {"archived": 0}
        
        content = self.memory_md_path.read_text(encoding="utf-8")
        
        # Find entries to archive
        lines = content.split("\n")
        new_lines: list[str] = []
        archive_lines: list[str] = []
        
        for line in lines:
            # Check if line is an entry with date
            match = re.match(r"- \[(\d{4}-\d{2}-\d{2})\]", line)
            if match:
                entry_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                
                # Check importance marker
                is_important = "重要性: 5" in line or "重要性：5" in line
                
                if entry_date < cutoff_date and not is_important:
                    archive_lines.append(line)
                    archived += 1
                    continue
            
            new_lines.append(line)
        
        if archived > 0:
            # Create archive directory
            archive_dir = self.memory_path / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Write archive file
            archive_file = archive_dir / f"memory-archive-{datetime.now().strftime('%Y%m%d')}.md"
            archive_content = f"# 记忆归档 ({datetime.now().strftime('%Y-%m-%d')})\n\n"
            archive_content += "\n".join(archive_lines)
            
            archive_file.write_text(archive_content, encoding="utf-8")
            
            # Update MEMORY.md
            self.memory_md_path.write_text("\n".join(new_lines), encoding="utf-8")
            
            logger.info(
                "Memory entries archived",
                extra={"archived": archived, "archive_file": str(archive_file)}
            )
        
        return {"archived": archived}
    
    async def run_maintenance(self) -> dict[str, Any]:
        """Run full maintenance cycle.
        
        Executes all maintenance tasks:
        1. Process daily logs to MEMORY.md
        2. Cleanup old daily logs
        3. Archive old MEMORY.md entries
        
        Returns:
            Dict with maintenance results
        """
        start_time = datetime.now()
        
        try:
            # Process daily logs
            process_result = self.process_daily_logs_to_memory_md()
            
            # Cleanup old logs
            cleanup_result = self.cleanup_old_daily_logs()
            
            # Archive old entries
            archive_result = self.archive_old_memory_entries()
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            result = {
                "success": True,
                "processed_entries": process_result["processed"],
                "added_entries": process_result["added"],
                "removed_logs": cleanup_result["removed"],
                "archived_entries": archive_result["archived"],
                "duration_ms": duration_ms,
            }
            
            logger.info(
                "Maintenance cycle completed",
                extra=result
            )
            
            return result
            
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            logger.error(
                "Maintenance cycle failed",
                extra={"error": str(e), "duration_ms": duration_ms}
            )
            
            return {
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms,
            }
    
    def get_scheduler_config(self) -> dict[str, Any]:
        """Get scheduler configuration for APScheduler.
        
        T043: Returns configuration for scheduled maintenance.
        
        Returns:
            Dict with scheduler configuration
        """
        return {
            "schedule_time": "02:00",  # Run at 2 AM
            "min_importance": self.min_importance,
            "keep_days": self.keep_days,
            "timezone": "Asia/Shanghai",
        }


# Global scheduler instance
_scheduler: Any = None
_maintenance_service: MemoryMaintenanceService | None = None


def setup_scheduled_maintenance(
    workspace_path: str,
    llm_client: Any = None,
    schedule_time: str = "02:00",
) -> Any:
    """Setup scheduled maintenance with APScheduler.
    
    T043: Configures APScheduler for daily maintenance.
    
    Args:
        workspace_path: Path to workspace directory
        llm_client: Optional LLM client
        schedule_time: Time to run maintenance (HH:MM format)
        
    Returns:
        Scheduler instance
    """
    global _scheduler, _maintenance_service
    
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        _maintenance_service = MemoryMaintenanceService(
            workspace_path=workspace_path,
            llm_client=llm_client,
        )
        
        _scheduler = AsyncIOScheduler()
        
        # Parse schedule time
        hour, minute = map(int, schedule_time.split(":"))
        
        # Add daily maintenance job
        _scheduler.add_job(
            _maintenance_service.run_maintenance,
            CronTrigger(hour=hour, minute=minute),
            id="memory_maintenance",
            name="Daily Memory Maintenance",
            replace_existing=True,
        )
        
        logger.info(
            "Scheduled maintenance configured",
            extra={"schedule_time": schedule_time}
        )
        
        return _scheduler
        
    except ImportError:
        logger.warning(
            "APScheduler not installed, scheduled maintenance disabled"
        )
        return None


def start_scheduler() -> None:
    """Start the maintenance scheduler."""
    global _scheduler
    
    if _scheduler:
        _scheduler.start()
        logger.info("Maintenance scheduler started")


def stop_scheduler() -> None:
    """Stop the maintenance scheduler."""
    global _scheduler
    
    if _scheduler:
        _scheduler.shutdown()
        logger.info("Maintenance scheduler stopped")


def get_maintenance_service(
    workspace_path: str | None = None,
) -> MemoryMaintenanceService | None:
    """Get the global maintenance service instance.
    
    Args:
        workspace_path: Optional workspace path to create new service
        
    Returns:
        MemoryMaintenanceService instance or None
    """
    global _maintenance_service
    
    if _maintenance_service is None and workspace_path:
        _maintenance_service = MemoryMaintenanceService(workspace_path)
    
    return _maintenance_service
