"""
Memory storage service for the x-agent2 AI assistant system.

This module handles the storage and retrieval of memory entries,
including short-term and long-term memory management.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from uuid import UUID
import json
import asyncio
from enum import Enum

from src.db.models.memory_entry import MemoryEntry
from src.db.models.user import User
from src.agent_core.config.config_service import get_config


class MemoryType(Enum):
    """Types of memory entries."""
    EPISODIC = "episodic"      # Personal experiences and events
    SEMANTIC = "semantic"      # Facts and general knowledge
    PROCEDURAL = "procedural"  # Skills and procedures
    WORKING = "working"        # Short-term memory for current tasks
    LONG_TERM = "long_term"    # Long-term memory for persistent knowledge


class ExpirationPolicy(Enum):
    """Expiration policies for memory entries."""
    TEMPORARY = "temporary"      # Expires after a short time
    SESSION = "session"          # Expires when session ends
    USER_DEFINED = "user_defined" # Expires based on user-defined time
    NEVER = "never"              # Does not expire automatically


class MemoryStorageService:
    """Service class for managing memory storage operations."""

    def __init__(self):
        self.config = get_config()
        self.default_ttl = timedelta(hours=24)  # Default time-to-live for temporary memories

    async def store_memory(
        self,
        user_id: str,
        content: Union[str, Dict[str, Any]],
        memory_type: MemoryType,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        expiration_policy: ExpirationPolicy = ExpirationPolicy.TEMPORARY,
        ttl: Optional[timedelta] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a new memory entry.

        Args:
            user_id: ID of the user associated with the memory
            content: Content of the memory (string or structured data)
            memory_type: Type of memory being stored
            context: Contextual information about the memory
            tags: Tags for categorizing the memory
            expiration_policy: Policy for when the memory expires
            ttl: Time-to-live for temporary memories
            metadata: Additional metadata about the memory

        Returns:
            ID of the created memory entry
        """
        # Ensure content is stored as a string
        if isinstance(content, dict):
            content_str = json.dumps(content)
        else:
            content_str = str(content)

        # Determine expiration time based on policy
        expires_at = None
        if expiration_policy == ExpirationPolicy.TEMPORARY:
            ttl = ttl or self.default_ttl
            expires_at = datetime.utcnow() + ttl
        elif expiration_policy == ExpirationPolicy.USER_DEFINED and ttl:
            expires_at = datetime.utcnow() + ttl
        elif expiration_policy == ExpirationPolicy.SESSION:
            # Session-based expiration would need to be handled elsewhere
            expires_at = datetime.utcnow() + timedelta(hours=1)  # Default session length

        # Create memory entry
        memory_entry = MemoryEntry(
            id=None,  # Will be auto-generated
            user_id=user_id,
            content=content_str,
            memory_type=memory_type.value,
            context=context or {},
            tags=tags or [],
            expires_at=expires_at,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            last_accessed_at=datetime.utcnow()
        )

        # Save to database
        await memory_entry.save()

        return memory_entry.id

    async def retrieve_memory(
        self,
        memory_id: str,
        user_id: Optional[str] = None
    ) -> Optional[MemoryEntry]:
        """
        Retrieve a specific memory entry by ID.

        Args:
            memory_id: ID of the memory to retrieve
            user_id: Optional user ID to verify ownership

        Returns:
            Memory entry if found and accessible, None otherwise
        """
        try:
            memory = await MemoryEntry.get_by_id(memory_id)

            # Verify user ownership if user_id provided
            if user_id and memory.user_id != user_id:
                return None

            # Check if memory has expired
            if memory.expires_at and memory.expires_at < datetime.utcnow():
                await self.purge_expired_memories([memory_id])
                return None

            # Update last accessed time
            await memory.update(last_accessed_at=datetime.utcnow())

            return memory
        except Exception:
            return None

    async def retrieve_memories_by_type(
        self,
        user_id: str,
        memory_type: MemoryType,
        limit: int = 50,
        offset: int = 0
    ) -> List[MemoryEntry]:
        """
        Retrieve memories of a specific type for a user.

        Args:
            user_id: ID of the user whose memories to retrieve
            memory_type: Type of memories to retrieve
            limit: Maximum number of memories to return
            offset: Number of memories to skip

        Returns:
            List of memory entries
        """
        try:
            memories = await MemoryEntry.get_by_user_and_type(
                user_id,
                memory_type.value,
                limit,
                offset
            )

            # Filter out expired memories and update access times
            valid_memories = []
            expired_ids = []

            for memory in memories:
                if memory.expires_at and memory.expires_at < datetime.utcnow():
                    expired_ids.append(memory.id)
                else:
                    await memory.update(last_accessed_at=datetime.utcnow())
                    valid_memories.append(memory)

            # Purge expired memories asynchronously
            if expired_ids:
                asyncio.create_task(self.purge_expired_memories(expired_ids))

            return valid_memories
        except Exception:
            return []

    async def search_memories(
        self,
        user_id: str,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[MemoryEntry]:
        """
        Search for memories matching a query.

        Args:
            user_id: ID of the user whose memories to search
            query: Query string to search for
            memory_types: Optional list of memory types to search within
            tags: Optional list of tags to filter by
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of memory entries matching the query
        """
        try:
            # Convert memory types to string values
            type_values = [mt.value for mt in memory_types] if memory_types else None

            # Perform search
            memories = await MemoryEntry.search(
                user_id,
                query,
                type_values,
                tags,
                limit,
                offset
            )

            # Filter out expired memories and update access times
            valid_memories = []
            expired_ids = []

            for memory in memories:
                if memory.expires_at and memory.expires_at < datetime.utcnow():
                    expired_ids.append(memory.id)
                else:
                    await memory.update(last_accessed_at=datetime.utcnow())
                    valid_memories.append(memory)

            # Purge expired memories asynchronously
            if expired_ids:
                asyncio.create_task(self.purge_expired_memories(expired_ids))

            return valid_memories
        except Exception:
            return []

    async def update_memory(
        self,
        memory_id: str,
        user_id: str,
        content: Optional[Union[str, Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing memory entry.

        Args:
            memory_id: ID of the memory to update
            user_id: ID of the user (for verification)
            content: New content for the memory
            context: New context for the memory
            tags: New tags for the memory
            metadata: New metadata for the memory

        Returns:
            True if update was successful, False otherwise
        """
        try:
            memory = await MemoryEntry.get_by_id(memory_id)

            # Verify user ownership
            if memory.user_id != user_id:
                return False

            # Update fields if provided
            updates = {}
            if content is not None:
                if isinstance(content, dict):
                    updates['content'] = json.dumps(content)
                else:
                    updates['content'] = str(content)
            if context is not None:
                updates['context'] = context
            if tags is not None:
                updates['tags'] = tags
            if metadata is not None:
                updates['metadata'] = metadata

            # Update last modified time
            updates['last_modified_at'] = datetime.utcnow()

            await memory.update(**updates)
            return True
        except Exception:
            return False

    async def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """
        Delete a specific memory entry.

        Args:
            memory_id: ID of the memory to delete
            user_id: ID of the user (for verification)

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            memory = await MemoryEntry.get_by_id(memory_id)

            # Verify user ownership
            if memory.user_id != user_id:
                return False

            await memory.delete()
            return True
        except Exception:
            return False

    async def delete_memories_by_tags(self, user_id: str, tags: List[str]) -> int:
        """
        Delete all memories with specific tags.

        Args:
            user_id: ID of the user whose memories to delete
            tags: List of tags to match for deletion

        Returns:
            Number of memories deleted
        """
        try:
            memories = await MemoryEntry.get_by_tags(user_id, tags)
            deleted_count = 0

            for memory in memories:
                if memory.user_id == user_id:
                    await memory.delete()
                    deleted_count += 1

            return deleted_count
        except Exception:
            return 0

    async def purge_expired_memories(self, memory_ids: Optional[List[str]] = None) -> int:
        """
        Permanently remove expired memory entries.

        Args:
            memory_ids: Specific memory IDs to check for expiration.
                       If None, checks all memories.

        Returns:
            Number of expired memories purged
        """
        try:
            if memory_ids:
                # Check specific memories
                purged_count = 0
                for memory_id in memory_ids:
                    memory = await MemoryEntry.get_by_id(memory_id)
                    if memory.expires_at and memory.expires_at < datetime.utcnow():
                        await memory.delete()
                        purged_count += 1
            else:
                # Find and purge all expired memories
                expired_memories = await MemoryEntry.get_expired_memories()
                purged_count = len(expired_memories)

                for memory in expired_memories:
                    await memory.delete()

            return purged_count
        except Exception:
            return 0

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics about a user's memories.

        Args:
            user_id: ID of the user to get stats for

        Returns:
            Dictionary with memory statistics
        """
        try:
            total_count = await MemoryEntry.count_by_user(user_id)
            type_counts = await MemoryEntry.count_by_user_and_type(user_id)
            expired_count = await MemoryEntry.count_expired_by_user(user_id)

            # Get the oldest and newest memory timestamps
            oldest_memory = await MemoryEntry.get_oldest_by_user(user_id)
            newest_memory = await MemoryEntry.get_newest_by_user(user_id)

            return {
                "total_memories": total_count,
                "memory_types": type_counts,
                "expired_memories": expired_count,
                "oldest_memory_date": oldest_memory.created_at.isoformat() if oldest_memory else None,
                "newest_memory_date": newest_memory.created_at.isoformat() if newest_memory else None
            }
        except Exception:
            return {
                "total_memories": 0,
                "memory_types": {},
                "expired_memories": 0,
                "oldest_memory_date": None,
                "newest_memory_date": None
            }

    async def export_memories(self, user_id: str, memory_type: Optional[MemoryType] = None) -> str:
        """
        Export a user's memories to a serialized format.

        Args:
            user_id: ID of the user whose memories to export
            memory_type: Optional specific type of memories to export

        Returns:
            JSON string containing the exported memories
        """
        try:
            if memory_type:
                memories = await self.retrieve_memories_by_type(user_id, memory_type, limit=1000)
            else:
                memories = await MemoryEntry.get_by_user(user_id, limit=1000)

            # Prepare export data
            export_data = {
                "user_id": user_id,
                "export_date": datetime.utcnow().isoformat(),
                "memories": [
                    {
                        "id": mem.id,
                        "content": mem.content,
                        "memory_type": mem.memory_type,
                        "context": mem.context,
                        "tags": mem.tags,
                        "metadata": mem.metadata,
                        "created_at": mem.created_at.isoformat(),
                        "last_accessed_at": mem.last_accessed_at.isoformat(),
                        "expires_at": mem.expires_at.isoformat() if mem.expires_at else None
                    }
                    for mem in memories
                ]
            }

            return json.dumps(export_data, indent=2)
        except Exception:
            return json.dumps({"error": "Failed to export memories"}, indent=2)

    async def import_memories(self, user_id: str, export_data: str) -> int:
        """
        Import memories from a serialized format.

        Args:
            user_id: ID of the user to import memories for
            export_data: JSON string containing memories to import

        Returns:
            Number of memories imported
        """
        try:
            import_data = json.loads(export_data)
            imported_count = 0

            for mem_data in import_data.get("memories", []):
                # Create a new memory with the user_id (ignore the original ID to prevent conflicts)
                new_memory = MemoryEntry(
                    id=None,  # Auto-generate new ID
                    user_id=user_id,
                    content=mem_data["content"],
                    memory_type=mem_data["memory_type"],
                    context=mem_data["context"],
                    tags=mem_data["tags"],
                    metadata=mem_data["metadata"],
                    created_at=datetime.fromisoformat(mem_data["created_at"]),
                    last_accessed_at=datetime.fromisoformat(mem_data["last_accessed_at"]) if mem_data["last_accessed_at"] else datetime.utcnow(),
                    expires_at=datetime.fromisoformat(mem_data["expires_at"]) if mem_data["expires_at"] else None
                )

                await new_memory.save()
                imported_count += 1

            return imported_count
        except Exception:
            return 0


class MemoryRetrievalService:
    """Service for retrieving and organizing memories."""

    def __init__(self, storage_service: MemoryStorageService):
        self.storage_service = storage_service

    async def get_recent_memories(
        self,
        user_id: str,
        count: int = 10,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryEntry]:
        """Get the most recent memories for a user."""
        try:
            memories = await MemoryEntry.get_recent_by_user(
                user_id,
                count,
                [mt.value for mt in memory_types] if memory_types else None
            )

            # Filter expired and update access times
            valid_memories = []
            expired_ids = []

            for memory in memories:
                if memory.expires_at and memory.expires_at < datetime.utcnow():
                    expired_ids.append(memory.id)
                else:
                    await memory.update(last_accessed_at=datetime.utcnow())
                    valid_memories.append(memory)

            if expired_ids:
                asyncio.create_task(self.storage_service.purge_expired_memories(expired_ids))

            return valid_memories
        except Exception:
            return []

    async def get_working_memory(self, user_id: str) -> List[MemoryEntry]:
        """Get working memory (short-term) for a user."""
        return await self.storage_service.retrieve_memories_by_type(
            user_id,
            MemoryType.WORKING
        )

    async def get_long_term_memory(self, user_id: str) -> List[MemoryEntry]:
        """Get long-term memory for a user."""
        return await self.storage_service.retrieve_memories_by_type(
            user_id,
            MemoryType.LONG_TERM
        )


# Global memory storage service instance
memory_storage_service = MemoryStorageService()
memory_retrieval_service = MemoryRetrievalService(memory_storage_service)


# Convenience functions
async def store_memory(
    user_id: str,
    content: Union[str, Dict[str, Any]],
    memory_type: MemoryType,
    context: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None
) -> str:
    """Store a memory entry."""
    return await memory_storage_service.store_memory(
        user_id, content, memory_type, context, tags
    )


async def retrieve_memory(memory_id: str, user_id: str) -> Optional[MemoryEntry]:
    """Retrieve a specific memory entry."""
    return await memory_storage_service.retrieve_memory(memory_id, user_id)


async def search_memories(user_id: str, query: str, tags: Optional[List[str]] = None) -> List[MemoryEntry]:
    """Search for memories."""
    return await memory_storage_service.search_memories(user_id, query, tags=tags)