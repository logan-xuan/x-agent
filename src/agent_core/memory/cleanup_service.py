"""
Memory cleanup and expiry management service for the x-agent2 AI assistant system.

This module handles the automatic cleanup of expired memories and manages
memory lifecycle according to configured policies.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import logging
from enum import Enum

from src.db.models.memory_entry import MemoryEntry
from src.agent_core.memory.storage_service import MemoryStorageService, MemoryType
from src.agent_core.config.config_service import get_config


class CleanupPolicy(Enum):
    """Policies for memory cleanup."""
    TIME_BASED = "time_based"
    SIZE_BASED = "size_based"
    ACCESS_COUNT_BASED = "access_count_based"
    COMBINED = "combined"


class ExpiryRule(Enum):
    """Rules for determining memory expiry."""
    TEMPORARY = "temporary"      # Expires after fixed time
    SESSION = "session"          # Expires when session ends
    INACTIVITY = "inactivity"    # Expires after period of inactivity
    CUSTOM = "custom"            # Custom expiry based on conditions


class MemoryCleanupService:
    """Service class for managing memory cleanup operations."""

    def __init__(self, storage_service: Optional[MemoryStorageService] = None):
        self.storage_service = storage_service or MemoryStorageService()
        self.config = get_config()

        # Default cleanup policies
        self.default_policies = {
            MemoryType.WORKING: timedelta(minutes=30),  # Working memory expires in 30 minutes
            MemoryType.EPISODIC: timedelta(days=30),   # Episodic memory expires after 30 days
            MemoryType.SEMANTIC: timedelta(days=365),  # Semantic memory expires after 1 year
            MemoryType.PROCEDURAL: timedelta(days=180), # Procedural memory expires after 6 months
            MemoryType.LONG_TERM: timedelta(days=730)   # Long-term memory expires after 2 years
        }

        # Configure logging
        self.logger = logging.getLogger(__name__)

    async def cleanup_expired_memories(self, user_id: Optional[str] = None) -> int:
        """
        Remove all expired memories for a user or system-wide.

        Args:
            user_id: Optional user ID to clean up for (if None, cleans up system-wide)

        Returns:
            Number of memories cleaned up
        """
        try:
            if user_id:
                expired_memories = await MemoryEntry.get_expired_by_user(user_id)
            else:
                expired_memories = await MemoryEntry.get_all_expired()

            count = len(expired_memories)

            # Delete each expired memory
            for memory in expired_memories:
                await memory.delete()

            self.logger.info(f"Cleaned up {count} expired memories{' for user ' + user_id if user_id else ' system-wide'}")
            return count
        except Exception as e:
            self.logger.error(f"Error cleaning up expired memories: {e}")
            return 0

    async def cleanup_inactive_memories(
        self,
        user_id: str,
        inactive_period: timedelta = timedelta(days=30)
    ) -> int:
        """
        Remove memories that haven't been accessed within the specified period.

        Args:
            user_id: ID of the user whose memories to check
            inactive_period: Period after which memories are considered inactive

        Returns:
            Number of inactive memories cleaned up
        """
        try:
            cutoff_time = datetime.utcnow() - inactive_period

            # Get memories for the user that haven't been accessed recently
            all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)
            inactive_memories = [
                m for m in all_memories
                if m.last_accessed_at and m.last_accessed_at < cutoff_time
            ]

            count = len(inactive_memories)

            # Delete inactive memories
            for memory in inactive_memories:
                await memory.delete()

            self.logger.info(f"Cleaned up {count} inactive memories for user {user_id}")
            return count
        except Exception as e:
            self.logger.error(f"Error cleaning up inactive memories: {e}")
            return 0

    async def cleanup_by_memory_type(
        self,
        user_id: str,
        memory_type: MemoryType,
        max_count: Optional[int] = None
    ) -> int:
        """
        Clean up memories of a specific type, optionally limiting to max_count.

        Args:
            user_id: ID of the user whose memories to clean up
            memory_type: Type of memories to clean up
            max_count: Optional maximum number of memories to remove

        Returns:
            Number of memories cleaned up
        """
        try:
            # Get memories of the specified type
            memories = await self.storage_service.retrieve_memories_by_type(
                user_id,
                memory_type
            )

            # If max_count specified, only clean up the oldest memories beyond the limit
            if max_count and len(memories) > max_count:
                # Sort by creation date (oldest first) and remove excess
                memories.sort(key=lambda x: x.created_at)
                memories_to_delete = memories[max_count:]
            else:
                # If no max_count specified, just return 0 as nothing needs to be cleaned
                return 0

            count = len(memories_to_delete)

            # Delete the excess memories
            for memory in memories_to_delete:
                await memory.delete()

            self.logger.info(f"Cleaned up {count} {memory_type.value} memories for user {user_id}")
            return count
        except Exception as e:
            self.logger.error(f"Error cleaning up {memory_type.value} memories: {e}")
            return 0

    async def apply_expiry_rules(
        self,
        user_id: str,
        rules: List[ExpiryRule],
        **conditions
    ) -> Dict[str, int]:
        """
        Apply specific expiry rules to a user's memories.

        Args:
            user_id: ID of the user whose memories to process
            rules: List of expiry rules to apply
            **conditions: Additional conditions for the rules

        Returns:
            Dictionary with counts of cleaned up memories by rule
        """
        results = {}

        for rule in rules:
            if rule == ExpiryRule.TEMPORARY:
                # Clean up temporary memories that have exceeded their TTL
                temp_memories = await self._get_temporary_memories(user_id)
                count = 0
                for memory in temp_memories:
                    if memory.expires_at and memory.expires_at < datetime.utcnow():
                        await memory.delete()
                        count += 1
                results[rule.value] = count

            elif rule == ExpiryRule.SESSION:
                # Clean up session-based memories
                session_id = conditions.get('session_id')
                if session_id:
                    session_memories = await self._get_session_memories(user_id, session_id)
                    count = 0
                    for memory in session_memories:
                        await memory.delete()
                        count += 1
                    results[rule.value] = count
                else:
                    results[rule.value] = 0

            elif rule == ExpiryRule.INACTIVITY:
                # Use the inactivity-based cleanup
                inactive_days = conditions.get('inactive_days', 30)
                count = await self.cleanup_inactive_memories(
                    user_id,
                    timedelta(days=inactive_days)
                )
                results[rule.value] = count

            elif rule == ExpiryRule.CUSTOM:
                # Apply custom conditions
                count = await self._apply_custom_expiry(user_id, conditions)
                results[rule.value] = count

        return results

    async def _get_temporary_memories(self, user_id: str) -> List[MemoryEntry]:
        """Get temporary memories for a user."""
        # For this implementation, we'll consider working memory as temporary
        return await self.storage_service.retrieve_memories_by_type(
            user_id,
            MemoryType.WORKING
        )

    async def _get_session_memories(self, user_id: str, session_id: str) -> List[MemoryEntry]:
        """Get session-specific memories for a user."""
        all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)
        return [m for m in all_memories if m.metadata.get('session_id') == session_id]

    async def _apply_custom_expiry(self, user_id: str, conditions: Dict[str, Any]) -> int:
        """Apply custom expiry logic based on provided conditions."""
        try:
            # This is a placeholder implementation - would be customized based on conditions
            # For example, remove memories with certain tags, or based on content patterns
            all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)

            # Example condition: remove memories with specific tags
            if 'remove_tags' in conditions:
                remove_tags = conditions['remove_tags']
                memories_to_remove = [m for m in all_memories if any(tag in remove_tags for tag in m.tags)]
            # Example condition: remove memories with certain content patterns
            elif 'content_contains' in conditions:
                content_pattern = conditions['content_contains']
                memories_to_remove = [m for m in all_memories if content_pattern.lower() in m.content.lower()]
            else:
                # If no known conditions, return 0
                return 0

            count = len(memories_to_remove)
            for memory in memories_to_remove:
                await memory.delete()

            return count
        except Exception as e:
            self.logger.error(f"Error applying custom expiry: {e}")
            return 0

    async def get_cleanup_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics about memory cleanup for a user.

        Args:
            user_id: ID of the user to get statistics for

        Returns:
            Dictionary with cleanup statistics
        """
        try:
            # Get all memories for the user
            all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)
            total_count = len(all_memories)

            # Count by type
            type_counts = {}
            for memory in all_memories:
                memory_type = memory.memory_type
                type_counts[memory_type] = type_counts.get(memory_type, 0) + 1

            # Count expired memories
            expired_memories = await MemoryEntry.get_expired_by_user(user_id)
            expired_count = len(expired_memories)

            # Count memories by age
            now = datetime.utcnow()
            current_count = 0
            aged_1_7_days = 0
            aged_8_30_days = 0
            aged_over_30_days = 0

            for memory in all_memories:
                age = (now - memory.created_at).days
                if age == 0:
                    current_count += 1
                elif 1 <= age <= 7:
                    aged_1_7_days += 1
                elif 8 <= age <= 30:
                    aged_8_30_days += 1
                else:
                    aged_over_30_days += 1

            return {
                "total_memories": total_count,
                "memory_types": type_counts,
                "expired_memories": expired_count,
                "memories_by_age": {
                    "current_day": current_count,
                    "1_7_days": aged_1_7_days,
                    "8_30_days": aged_8_30_days,
                    "over_30_days": aged_over_30_days
                },
                "last_cleanup": getattr(self, '_last_cleanup', None)
            }
        except Exception as e:
            self.logger.error(f"Error getting cleanup statistics: {e}")
            return {
                "total_memories": 0,
                "memory_types": {},
                "expired_memories": 0,
                "memories_by_age": {},
                "last_cleanup": None
            }

    async def schedule_cleanup_job(
        self,
        user_id: str,
        interval_minutes: int = 60,
        cleanup_types: List[MemoryType] = None
    ) -> str:
        """
        Schedule a recurring cleanup job for a user.

        Args:
            user_id: ID of the user to schedule cleanup for
            interval_minutes: Interval between cleanup jobs in minutes
            cleanup_types: Optional list of memory types to clean up (None means all)

        Returns:
            Job ID for the scheduled cleanup
        """
        # In a real implementation, this would use a task scheduler
        # For this example, we'll just simulate scheduling
        job_id = f"cleanup_job_{user_id}_{datetime.utcnow().timestamp()}"

        # Start background cleanup task
        asyncio.create_task(
            self._run_scheduled_cleanup(
                user_id,
                interval_minutes,
                cleanup_types,
                job_id
            )
        )

        return job_id

    async def _run_scheduled_cleanup(
        self,
        user_id: str,
        interval_minutes: int,
        cleanup_types: List[MemoryType],
        job_id: str
    ):
        """
        Internal method to run scheduled cleanup jobs.
        """
        try:
            while True:
                # Perform cleanup
                if cleanup_types:
                    # Clean up specific types
                    for memory_type in cleanup_types:
                        await self.cleanup_by_memory_type(user_id, memory_type)
                else:
                    # Clean up all expired memories
                    await self.cleanup_expired_memories(user_id)

                # Update last cleanup time
                self._last_cleanup = datetime.utcnow()

                # Sleep for the specified interval
                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            self.logger.info(f"Scheduled cleanup job {job_id} cancelled")
        except Exception as e:
            self.logger.error(f"Error in scheduled cleanup job {job_id}: {e}")

    async def perform_maintenance_cleanup(self) -> Dict[str, Any]:
        """
        Perform system-wide maintenance cleanup.

        Returns:
            Dictionary with maintenance statistics
        """
        start_time = datetime.utcnow()

        try:
            # Clean up all expired memories system-wide
            expired_count = await self.cleanup_expired_memories()

            # Get statistics after cleanup
            total_memories_after = await MemoryEntry.count_all()

            maintenance_time = (datetime.utcnow() - start_time).total_seconds()

            return {
                "expired_memories_removed": expired_count,
                "total_memories_after_cleanup": total_memories_after,
                "maintenance_duration_seconds": maintenance_time,
                "status": "completed"
            }
        except Exception as e:
            self.logger.error(f"Error during maintenance cleanup: {e}")
            return {
                "expired_memories_removed": 0,
                "total_memories_after_cleanup": 0,
                "maintenance_duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "status": "error",
                "error": str(e)
            }

    async def get_memory_lifespan_recommendations(
        self,
        user_id: str
    ) -> Dict[MemoryType, timedelta]:
        """
        Get recommended lifespans for different memory types based on usage patterns.

        Args:
            user_id: ID of the user to analyze

        Returns:
            Dictionary mapping memory types to recommended lifespans
        """
        try:
            # Analyze the user's memory access patterns
            all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)

            recommendations = {}
            for memory_type in MemoryType:
                memories_of_type = [m for m in all_memories if m.memory_type == memory_type.value]

                if not memories_of_type:
                    # If no memories of this type, use default
                    recommendations[memory_type] = self.default_policies.get(memory_type, timedelta(days=30))
                    continue

                # Calculate average access frequency
                total_accesses = sum(1 for m in memories_of_type if m.access_count and m.access_count > 0)
                avg_accesses = total_accesses / len(memories_of_type) if memories_of_type else 0

                # Calculate average age of frequently accessed memories
                recent_access_threshold = datetime.utcnow() - timedelta(days=7)
                frequently_accessed = [
                    m for m in memories_of_type
                    if m.last_accessed_at and m.last_accessed_at > recent_access_threshold
                ]

                # Determine lifespan based on access patterns
                if len(frequently_accessed) > len(memories_of_type) * 0.5:
                    # Highly accessed memories - longer lifespan
                    base_lifespan = self.default_policies.get(memory_type, timedelta(days=30))
                    recommendations[memory_type] = base_lifespan * 2
                elif avg_accesses > 2:
                    # Moderately accessed memories - default lifespan
                    recommendations[memory_type] = self.default_policies.get(memory_type, timedelta(days=30))
                else:
                    # Rarely accessed memories - shorter lifespan
                    base_lifespan = self.default_policies.get(memory_type, timedelta(days=30))
                    recommendations[memory_type] = max(timedelta(days=1), base_lifespan / 2)

            return recommendations
        except Exception as e:
            self.logger.error(f"Error getting memory lifespan recommendations: {e}")
            # Return default policies in case of error
            return self.default_policies


class GarbageCollectionService:
    """Service for performing garbage collection on memory stores."""

    def __init__(self, cleanup_service: MemoryCleanupService):
        self.cleanup_service = cleanup_service
        self.logger = logging.getLogger(__name__)

    async def full_garbage_collection(self) -> Dict[str, Any]:
        """Perform a full garbage collection sweep."""
        start_time = datetime.utcnow()

        try:
            # Clean up expired memories
            expired_count = await self.cleanup_service.cleanup_expired_memories()

            # Clean up any other stale entries if needed
            # (in a real system, this might include cleaning up orphaned references, etc.)

            gc_time = (datetime.utcnow() - start_time).total_seconds()

            return {
                "garbage_collected_entries": expired_count,
                "gc_duration_seconds": gc_time,
                "status": "completed"
            }
        except Exception as e:
            self.logger.error(f"Error during garbage collection: {e}")
            return {
                "garbage_collected_entries": 0,
                "gc_duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "status": "error",
                "error": str(e)
            }


# Global memory cleanup service instance
memory_cleanup_service = MemoryCleanupService()
garbage_collection_service = GarbageCollectionService(memory_cleanup_service)


# Convenience functions
async def cleanup_expired_memories(user_id: Optional[str] = None) -> int:
    """Clean up expired memories for a user or system-wide."""
    return await memory_cleanup_service.cleanup_expired_memories(user_id)


async def cleanup_inactive_memories(user_id: str, inactive_period: timedelta = timedelta(days=30)) -> int:
    """Clean up inactive memories for a user."""
    return await memory_cleanup_service.cleanup_inactive_memories(user_id, inactive_period)


async def perform_maintenance_cleanup() -> Dict[str, Any]:
    """Perform system-wide maintenance cleanup."""
    return await memory_cleanup_service.perform_maintenance_cleanup()