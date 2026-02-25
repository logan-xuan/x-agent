"""Error Learning and Memory Integration Service.

This service integrates memory capabilities into the error correction workflow:
1. Detect frequent error patterns
2. Extract lessons learned using LLM after successful correction
3. Write experiences to long-term memory
4. Retrieve relevant memories when similar errors occur
5. Inject retrieved experiences into reflection context to aid correction

Key Features:
- Error pattern recognition across sessions
- Automatic lesson extraction via LLM
- Hybrid search for similar past experiences
- Dynamic memory injection during ReAct loop
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..memory.md_sync import MarkdownSync, get_md_sync
from ..memory.models import MemoryEntry, MemoryContentType
from ..services.llm.router import LLMRouter
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ErrorPattern:
    """Represents a recurring error pattern."""
    error_type: str
    error_message: str
    tool_name: str
    occurrence_count: int = 1
    last_occurrence: float = field(default_factory=time.time)
    session_ids: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    max_age_seconds: float = field(default=604800)  # 7 days
    
    def is_frequent(self, threshold: int = 3) -> bool:
        """Check if this error occurs frequently."""
        return self.occurrence_count >= threshold
    
    def is_expired(self) -> bool:
        """Check if this pattern has expired."""
        return (time.time() - self.last_occurrence) > self.max_age_seconds


@dataclass
class LearnedLesson:
    """A lesson learned from error correction."""
    error_pattern: ErrorPattern
    lesson_content: str
    solution_summary: str
    extracted_at: datetime = field(default_factory=datetime.now)
    confidence_score: float = 0.0  # How confident we are in this lesson


class ErrorLearningService:
    """Service for learning from errors and leveraging memory for correction."""
    
    def __init__(self, llm_router: LLMRouter):
        """Initialize the error learning service.
        
        Args:
            llm_router: LLM router for extracting lessons
        """
        self.llm_router = llm_router
        self.md_sync: MarkdownSync | None = None
        
        # Error pattern tracking
        self.error_patterns: dict[str, ErrorPattern] = {}
        self.learned_lessons: list[LearnedLesson] = []
        
        # Configuration
        self.frequent_error_threshold = 3  # Min occurrences to be "frequent"
        self.memory_min_score = 0.6  # Minimum relevance score for memory retrieval
        
        # ✅ OPTIMIZE: Add cleanup mechanism to prevent memory leak
        self.cleanup_interval_seconds = 3600  # Clean every hour
        self.last_cleanup_time = time.time()
        
        # ✅ OPTIMIZE: Add metrics tracking
        from dataclasses import dataclass, field
        @dataclass
        class ServiceMetrics:
            total_errors_recorded: int = 0
            total_lessons_extracted: int = 0
            total_memories_retrieved: int = 0
            average_retrieval_time_ms: float = 0.0
            retrieval_timeout_count: int = 0
            memory_write_failures: int = 0
            deduplication_saves: int = 0
        
        self.metrics = ServiceMetrics()
        
    def set_md_sync(self, md_sync: MarkdownSync):
        """Set the markdown sync instance for memory operations."""
        self.md_sync = md_sync
    
    def _cleanup_old_patterns(self):
        """Remove expired error patterns to prevent memory leak."""
        current_time = time.time()
        if current_time - self.last_cleanup_time < self.cleanup_interval_seconds:
            return
        
        expired_keys = [
            key for key, pattern in self.error_patterns.items()
            if pattern.is_expired()
        ]
        
        for key in expired_keys:
            del self.error_patterns[key]
        
        self.last_cleanup_time = current_time
        logger.info(
            "Cleaned up expired error patterns",
            extra={"removed_count": len(expired_keys)}
        )
    
    def record_error(
        self,
        error_type: str,
        error_message: str,
        tool_name: str,
        session_id: str,
        context: dict[str, Any] | None = None,
    ):
        """Record an error occurrence for pattern detection.
        
        Args:
            error_type: Type of error (e.g., "MODULE_NOT_FOUND")
            error_message: Full error message
            tool_name: Name of the tool that failed
            session_id: Current session ID
            context: Additional context information
        """
        # ✅ OPTIMIZE: Cleanup old patterns before recording new ones
        self._cleanup_old_patterns()
        
        # Create pattern key
        pattern_key = f"{error_type}:{tool_name}:{self._normalize_error(error_message)}"
        
        # Update or create pattern
        if pattern_key not in self.error_patterns:
            self.error_patterns[pattern_key] = ErrorPattern(
                error_type=error_type,
                error_message=error_message,
                tool_name=tool_name,
            )
        
        pattern = self.error_patterns[pattern_key]
        pattern.occurrence_count += 1
        pattern.last_occurrence = time.time()
        
        if session_id not in pattern.session_ids:
            pattern.session_ids.append(session_id)
        
        logger.info(
            "Error recorded",
            extra={
                "pattern_key": pattern_key,
                "occurrence_count": pattern.occurrence_count,
                "is_frequent": pattern.is_frequent(self.frequent_error_threshold),
            }
        )
    
    def _normalize_error(self, error_message: str) -> str:
        """Normalize error message for pattern matching."""
        # Remove specific paths and IDs to generalize patterns
        import re
        normalized = error_message.lower()
        normalized = re.sub(r'/[^\s]+/', '[PATH]', normalized)
        normalized = re.sub(r'\b[0-9a-f]{8,}\b', '[ID]', normalized)
        return normalized[:200]  # Truncate for brevity
    
    async def extract_lesson_after_correction(
        self,
        error_type: str,
        error_message: str,
        tool_name: str,
        correction_applied: str,
        session_id: str,
    ) -> str | None:
        """Extract and record a lesson learned after successful error correction.
        
        Args:
            error_type: Type of error that was corrected
            error_message: Original error message
            tool_name: Tool that failed
            correction_applied: Description of how it was fixed
            session_id: Session where correction occurred
            
        Returns:
            The extracted lesson content if successful, None otherwise
        """
        try:
            # Use LLM to extract lesson
            prompt = self._create_lesson_extraction_prompt(
                error_type, error_message, tool_name, correction_applied
            )
            
            response = await self.llm_router.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for focused extraction
            )
            
            lesson_content = response.content.strip()
            
            if lesson_content:
                # Create learned lesson
                lesson = LearnedLesson(
                    error_pattern=ErrorPattern(
                        error_type=error_type,
                        error_message=error_message,
                        tool_name=tool_name,
                    ),
                    lesson_content=lesson_content,
                    solution_summary=correction_applied[:500],
                    confidence_score=self._calculate_confidence(correction_applied),
                )
                
                self.learned_lessons.append(lesson)
                
                # Write to memory
                await self._write_lesson_to_memory(lesson, session_id)
                
                logger.info(
                    "Lesson extracted and recorded",
                    extra={
                        "error_type": error_type,
                        "tool_name": tool_name,
                        "confidence": lesson.confidence_score,
                    }
                )
                
                return lesson_content
            
        except Exception as e:
            logger.warning(
                "Failed to extract lesson",
                extra={"error": str(e), "error_type": error_type}
            )
        
        return None
    
    def _create_lesson_extraction_prompt(
        self,
        error_type: str,
        error_message: str,
        tool_name: str,
        correction_applied: str,
    ) -> str:
        """Create prompt for LLM to extract lesson from error correction."""
        return f"""你是一个经验丰富的 AI 助手专家。请从以下错误纠正案例中提取宝贵的经验教训。

## 错误信息
- **错误类型**: {error_type}
- **工具名称**: {tool_name}
- **错误详情**: {error_message[:500]}

## 纠正措施
{correction_applied}

## 任务
请提取这个案例中的经验教训，格式如下：

### 经验教训总结
[用 2-3 句话概括核心教训]

### 根本原因
[深入分析问题根源，而非表面症状]

### 解决方案模板
[提供可复用的解决步骤，包含具体代码示例]

### 预防措施
[如何避免同类问题再次发生]

### 适用场景
[这个经验可以用于哪些其他情况]

### 关键词
[3-5 个便于检索的关键词]

要求：
1. 教训要具体、可操作，避免空泛
2. 提供代码示例或配置示例
3. 说明这个经验的适用范围
4. 语言简洁明了，便于未来检索和应用

请直接输出格式化后的内容，不需要额外说明。"""
    
    def _calculate_confidence(self, correction_applied: str) -> float:
        """Calculate confidence score based on multiple quality indicators."""
        score = 0.5
        quality_indicators = 0
        
        # 1. Length indicates detail level
        if len(correction_applied) > 300:
            score += 0.15
            quality_indicators += 1
        elif len(correction_applied) > 150:
            score += 0.1
            quality_indicators += 1
        
        # 2. Contains structured code blocks
        if "```python" in correction_applied or "```js" in correction_applied:
            score += 0.15
            quality_indicators += 1
        elif "```" in correction_applied:
            score += 0.1
            quality_indicators += 1
        
        # 3. Contains specific file references (more precise than just ".py")
        import re
        if re.search(r'skills/\w+/scripts/[\w\.]+', correction_applied):
            score += 0.1
            quality_indicators += 1
        
        # 4. Contains step-by-step instructions
        if any(marker in correction_applied.lower() 
               for marker in ["step 1", "first", "then", "finally", "1.", "2."]):
            score += 0.1
            quality_indicators += 1
        
        # 5. Contains error message analysis
        if "error:" in correction_applied.lower() or "exception" in correction_applied.lower():
            score += 0.05
            quality_indicators += 1
        
        # Bonus for having multiple quality indicators
        if quality_indicators >= 4:
            score += 0.1
        
        return min(score, 1.0)
    
    async def _write_lesson_to_memory(self, lesson: LearnedLesson, session_id: str):
        """Write the learned lesson to memory system with deduplication."""
        if not self.md_sync:
            logger.warning("MD sync not available, skipping memory write")
            return
            
        try:
            # ✅ OPTIMIZE: Check for duplicates before writing
            entries = self.md_sync.list_all_entries(limit=1000)
            similar_entry = self._find_similar_lesson(entries, lesson)
                
            if similar_entry:
                logger.info(
                    "Similar lesson already exists in memory, skipping duplicate write",
                    extra={
                        "existing_entry_id": similar_entry.id,
                        "similarity_score": 0.95,
                    }
                )
                self.metrics.deduplication_saves += 1
                return
                
            # Create memory entry if no duplicate found
            memory_content = f"""## 错误学习：{lesson.error_pattern.error_type}

### 问题描述
错误类型：{lesson.error_pattern.error_type}
工具：{lesson.error_pattern.tool_name}
错误信息：{lesson.error_pattern.error_message[:300]}

### 经验教训
{lesson.lesson_content}

### 解决方案
{lesson.solution_summary}

### 元数据
- 置信度：{lesson.confidence_score:.2f}
- 学习时间：{lesson.extracted_at.isoformat()}
- 会话 ID: {session_id}
- 来源：AI 自动学习
"""
            
            entry = MemoryEntry(
                id=f"lesson-{datetime.now().strftime('%Y%m%d%H%M%S')}-{session_id[:8]}",
                content_type=MemoryContentType.SUMMARY,
                content=memory_content,
                created_at=datetime.now(),
                metadata={
                    "error_type": lesson.error_pattern.error_type,
                    "tool_name": lesson.error_pattern.tool_name,
                    "confidence": lesson.confidence_score,
                    "source": "error_learning",
                }
            )
            
            # Append to daily log
            self.md_sync.append_memory_entry(entry)
            
            logger.info(
                "Lesson written to memory",
                extra={
                    "entry_id": entry.id,
                    "error_type": lesson.error_pattern.error_type,
                }
            )
            
        except Exception as e:
            logger.error(
                "Failed to write lesson to memory",
                extra={"error": str(e), "lesson": str(lesson.error_pattern.error_type)}
            )
    
    def _find_similar_lesson(
        self, 
        entries: list[MemoryEntry], 
        lesson: LearnedLesson
    ) -> MemoryEntry | None:
        """Find if a similar lesson already exists in memory (deduplication)."""
        try:
            from ..memory.hybrid_search import get_hybrid_search
            from ..memory.vector_store import get_vector_store
            from ..memory.embedder import get_embedder
            
            vector_store = get_vector_store()
            embedder = get_embedder()
            hybrid_search = get_hybrid_search(vector_store=vector_store, embedder=embedder)
            
            # Search for similar content
            query = f"{lesson.error_pattern.error_type} {lesson.error_pattern.tool_name}"
            results = hybrid_search.search(
                query=query,
                entries=entries,
                limit=5,
                min_score=0.85,  # High threshold for deduplication
            )
            
            # Check if any result is very similar
            for result in results:
                if "error_learning" in result.entry.metadata.get('source', ''):
                    # Check content similarity
                    if self._content_similarity(result.entry.content, lesson.lesson_content) > 0.9:
                        return result.entry
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to check for duplicate lesson: {e}")
            return None
    
    def _content_similarity(self, text1: str, text2: str) -> float:
        """Simple cosine similarity for text deduplication using TF-IDF."""
        import re
        from collections import Counter
        import math
        
        # Tokenize
        def tokenize(text):
            return re.findall(r'\w+', text.lower())
        
        tokens1 = tokenize(text1)
        tokens2 = tokenize(text2)
        
        # Calculate term frequency
        tf1 = Counter(tokens1)
        tf2 = Counter(tokens2)
        
        # Get all unique words
        all_words = set(tokens1) | set(tokens2)
        
        # Calculate cosine similarity
        dot_product = sum(tf1.get(word, 0) * tf2.get(word, 0) for word in all_words)
        norm1 = math.sqrt(sum(count ** 2 for count in tf1.values()))
        norm2 = math.sqrt(sum(count ** 2 for count in tf2.values()))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def retrieve_relevant_memories_for_error(
        self,
        error_type: str,
        error_message: str,
        tool_name: str,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant past experiences for current error with fallback strategies."""
        import time
        start_time = time.time()
        
        try:
            # Strategy 1: Try hybrid search if md_sync available
            if self.md_sync:
                try:
                    entries = self.md_sync.list_all_entries(limit=1000)
                    if entries:
                        # Create search query from error details
                        query = f"{error_type} {tool_name} {error_message[:100]}"
                        
                        # Import hybrid search
                        from ..memory.hybrid_search import get_hybrid_search
                        from ..memory.vector_store import get_vector_store
                        from ..memory.embedder import get_embedder
                        
                        # Initialize hybrid search
                        vector_store = get_vector_store()
                        embedder = get_embedder()
                        hybrid_search = get_hybrid_search(vector_store=vector_store, embedder=embedder)
                        
                        # Perform search
                        results = hybrid_search.search(
                            query=query,
                            entries=entries,
                            limit=5,
                            min_score=self.memory_min_score,
                        )
                        
                        # Filter for relevant content types
                        relevant_results = []
                        for result in results:
                            # Prioritize lessons and summaries
                            if any(keyword in result.entry.content.lower() 
                                  for keyword in ["经验教训", "错误", "解决方案", "lesson", "error"]):
                                relevant_results.append({
                                    "entry": result.entry,
                                    "score": result.score,
                                    "vector_score": result.vector_score,
                                    "text_score": result.text_score,
                                })
                        
                        if relevant_results:
                            logger.info(
                                "Retrieved relevant memories for error",
                                extra={
                                    "error_type": error_type,
                                    "results_count": len(relevant_results),
                                    "top_score": relevant_results[0]["score"] if relevant_results else 0,
                                }
                            )
                            self.metrics.total_memories_retrieved += 1
                            return relevant_results
                except Exception as e:
                    logger.warning(f"Hybrid search failed: {e}")
            
            # Strategy 2: Fallback to in-memory learned lessons
            if self.learned_lessons:
                try:
                    query_keywords = f"{error_type} {tool_name}".lower().split()
                    matched_lessons = []
                    
                    for lesson in self.learned_lessons:
                        content_lower = lesson.lesson_content.lower()
                        if any(keyword in content_lower for keyword in query_keywords):
                            matched_lessons.append({
                                "entry": MemoryEntry(
                                    id=lesson.error_pattern.error_type,
                                    content_type=MemoryContentType.SUMMARY,
                                    content=lesson.lesson_content,
                                    created_at=lesson.extracted_at,
                                ),
                                "score": 0.7,  # Fixed score for keyword match
                                "vector_score": 0.0,
                                "text_score": 0.7,
                            })
                    
                    if matched_lessons:
                        logger.info(
                            "Using in-memory lessons as fallback",
                            extra={"matched_count": len(matched_lessons)}
                        )
                        return sorted(matched_lessons, key=lambda x: x["score"], reverse=True)
                except Exception as e:
                    logger.warning(f"In-memory lesson search failed: {e}")
            
            # Strategy 3: Return empty (no matches found)
            logger.debug("No relevant memories found for error")
            return []
            
        finally:
            # Update metrics
            elapsed_ms = (time.time() - start_time) * 1000
            count = self.metrics.total_memories_retrieved
            avg = self.metrics.average_retrieval_time_ms
            self.metrics.average_retrieval_time_ms = (avg * count + elapsed_ms) / (count + 1) if count > 0 else elapsed_ms
    
    def create_memory_injection_prompt(
        self,
        retrieved_memories: list[dict[str, Any]],
        current_error_type: str,
        current_error_message: str,
    ) -> str:
        """Create a prompt to inject retrieved memories into reflection context.
        
        Args:
            retrieved_memories: List of relevant memory entries
            current_error_type: Current error type
            current_error_message: Current error message
            
        Returns:
            Formatted prompt for LLM
        """
        if not retrieved_memories:
            return ""
        
        prompt_parts = [
            "\n\n💡 **历史经验提醒**\n",
            "系统检测到当前错误与历史经验相似，以下是曾经的成功解决方案：\n"
        ]
        
        for i, memory in enumerate(retrieved_memories[:3], 1):  # Top 3 most relevant
            entry = memory["entry"]
            score = memory["score"]
            
            prompt_parts.append(f"""
#### 经验 {i} (相关度：{score:.2f})
**来源**: {entry.metadata.get('source', '未知') if entry.metadata else '未知'}
**内容**: 
{entry.content[:500]}...
""")
        
        prompt_parts.append("""
**请仔细阅读以上历史经验**：
1. 这些是之前成功解决类似问题的方法
2. 可以参考其思路，但要根据当前情况调整
3. 如果多个经验都指向同一解决方案，优先尝试该方法

**思考**：这些历史经验对解决当前问题有什么启发？
""")
        
        return "".join(prompt_parts)
    
    def get_error_statistics(self) -> dict[str, Any]:
        """Get statistics about error patterns and learned lessons."""
        frequent_errors = [
            p for p in self.error_patterns.values() 
            if p.is_frequent(self.frequent_error_threshold)
        ]
        
        return {
            "total_unique_patterns": len(self.error_patterns),
            "frequent_patterns_count": len(frequent_errors),
            "total_lessons_learned": len(self.learned_lessons),
            "high_confidence_lessons": sum(
                1 for l in self.learned_lessons if l.confidence_score >= 0.7
            ),
            "most_common_error_types": self._get_top_error_types(5),
        }
    
    def _get_top_error_types(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get most common error types."""
        error_type_counts: dict[str, int] = {}
        
        for pattern in self.error_patterns.values():
            error_type = pattern.error_type
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + pattern.occurrence_count
        
        sorted_types = sorted(
            error_type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return [{"error_type": t, "count": c} for t, c in sorted_types]


# Global service instance
_error_learning_service: ErrorLearningService | None = None
_service_lock = __import__('threading').Lock()  # ✅ OPTIMIZE: Thread-safe lock


def get_error_learning_service(llm_router: LLMRouter | None = None) -> ErrorLearningService:
    """Get or create the global error learning service instance (thread-safe)."""
    global _error_learning_service
    
    # ✅ OPTIMIZE: Double-checked locking for thread safety
    if _error_learning_service is None:
        with _service_lock:
            if _error_learning_service is None:
                if llm_router is None:
                    from ..services.llm.router import LLMRouter
                    from ..config.manager import ConfigManager
                    
                    config = ConfigManager().config
                    llm_router = LLMRouter(config.models)
                
                _error_learning_service = ErrorLearningService(llm_router)
                
                # Try to initialize md_sync
                try:
                    _error_learning_service.set_md_sync(get_md_sync())
                except Exception as e:
                    logger.warning(f"Failed to initialize md_sync for error learning: {e}")
    
    return _error_learning_service
