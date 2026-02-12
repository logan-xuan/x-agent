"""
Memory search API endpoint for the x-agent2 AI assistant system.

This module provides API endpoints for searching and managing memories.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import uuid

from src.agent_core.memory.storage_service import (
    memory_storage_service,
    MemoryType,
    ExpirationPolicy,
    store_memory,
    retrieve_memory,
    search_memories
)
from src.agent_core.memory.retrieval_service import (
    memory_retrieval_service,
    retrieve_by_similarity,
    retrieve_by_keywords,
    retrieve_contextual
)
from src.agent_core.memory.embedding_service import find_similar_memories
from src.agent_core.memory.cleanup_service import memory_cleanup_service
from src.agent_core.api_utils.response_handler import (
    APIResponse,
    APIExceptionHandler,
    create_success_response,
    create_error_response
)
from src.agent_core.security.tool_security import authenticate_user


router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("/")
async def create_memory(
    user_id: str,
    content: str,
    memory_type: MemoryType,
    context: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = Query(None),
    ttl_hours: Optional[int] = Query(None)
):
    """
    Create a new memory entry.

    Args:
        user_id: ID of the user creating the memory
        content: Content of the memory
        memory_type: Type of memory being created
        context: Contextual information for the memory
        tags: Tags to categorize the memory
        ttl_hours: Time-to-live in hours for temporary memories

    Returns:
        JSON response with the created memory details
    """
    try:
        # Validate input
        if not content or not content.strip():
            return create_error_response(
                message="Memory content is required",
                status_code=400
            )

        # Determine expiration policy and TTL
        expiration_policy = ExpirationPolicy.TEMPORARY if ttl_hours else ExpirationPolicy.NEVER
        ttl = timedelta(hours=ttl_hours) if ttl_hours else None

        # Store the memory
        memory_id = await store_memory(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            context=context or {},
            tags=tags or [],
            expiration_policy=expiration_policy,
            ttl=ttl
        )

        # Return success response
        return create_success_response(
            data={
                "memory_id": memory_id,
                "created_at": datetime.utcnow().isoformat(),
                "memory_type": memory_type.value,
                "content_preview": content[:100] + "..." if len(content) > 100 else content
            },
            message="Memory created successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to create memory"
        )


@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    user_id: str
):
    """
    Retrieve a specific memory by ID.

    Args:
        memory_id: ID of the memory to retrieve
        user_id: ID of the user requesting the memory

    Returns:
        JSON response with the memory details
    """
    try:
        memory = await retrieve_memory(memory_id, user_id)

        if not memory:
            return create_error_response(
                message="Memory not found or access denied",
                status_code=404
            )

        # Return memory details
        return create_success_response(
            data={
                "id": memory.id,
                "user_id": memory.user_id,
                "content": memory.content,
                "memory_type": memory.memory_type,
                "context": memory.context,
                "tags": memory.tags,
                "created_at": memory.created_at.isoformat(),
                "last_accessed_at": memory.last_accessed_at.isoformat() if memory.last_accessed_at else None,
                "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
                "metadata": memory.metadata
            },
            message="Memory retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to retrieve memory"
        )


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    user_id: str,
    content: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = Query(None),
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Update an existing memory entry.

    Args:
        memory_id: ID of the memory to update
        user_id: ID of the user updating the memory
        content: New content for the memory (optional)
        context: New context for the memory (optional)
        tags: New tags for the memory (optional)
        metadata: New metadata for the memory (optional)

    Returns:
        JSON response indicating success or failure
    """
    try:
        # Validate that at least one field is provided for update
        if all(v is None for v in [content, context, tags, metadata]):
            return create_error_response(
                message="At least one field (content, context, tags, or metadata) must be provided for update",
                status_code=400
            )

        # Update the memory
        success = await memory_storage_service.update_memory(
            memory_id=memory_id,
            user_id=user_id,
            content=content,
            context=context,
            tags=tags,
            metadata=metadata
        )

        if not success:
            return create_error_response(
                message="Memory not found or access denied",
                status_code=404
            )

        return create_success_response(
            message="Memory updated successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to update memory"
        )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    user_id: str
):
    """
    Delete a specific memory by ID.

    Args:
        memory_id: ID of the memory to delete
        user_id: ID of the user deleting the memory

    Returns:
        JSON response indicating success or failure
    """
    try:
        success = await memory_storage_service.delete_memory(memory_id, user_id)

        if not success:
            return create_error_response(
                message="Memory not found or access denied",
                status_code=404
            )

        return create_success_response(
            message="Memory deleted successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to delete memory"
        )


@router.get("/")
async def search_memories_endpoint(
    user_id: str,
    query: Optional[str] = Query(None, description="Search query"),
    memory_type: Optional[MemoryType] = Query(None, description="Filter by memory type"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """
    Search for memories using keyword matching.

    Args:
        user_id: ID of the user searching for memories
        query: Search query string
        memory_type: Filter by specific memory type
        tags: Filter by specific tags
        limit: Maximum number of results to return
        offset: Number of results to skip

    Returns:
        JSON response with search results
    """
    try:
        # Prepare filters
        memory_types = [memory_type] if memory_type else None

        # Perform search
        memories = await search_memories(
            user_id=user_id,
            query=query or "",
            tags=tags
        )

        # Apply memory type filter if specified
        if memory_types:
            memories = [m for m in memories if m.memory_type in [mt.value for mt in memory_types]]

        # Apply pagination
        start_idx = offset
        end_idx = start_idx + limit
        paginated_memories = memories[start_idx:end_idx]

        # Format results
        results = []
        for memory in paginated_memories:
            results.append({
                "id": memory.id,
                "content_preview": memory.content[:200] + "..." if len(memory.content) > 200 else memory.content,
                "memory_type": memory.memory_type,
                "tags": memory.tags,
                "created_at": memory.created_at.isoformat(),
                "last_accessed_at": memory.last_accessed_at.isoformat() if memory.last_accessed_at else None
            })

        return create_success_response(
            data={
                "results": results,
                "total_count": len(memories),
                "returned_count": len(results),
                "limit": limit,
                "offset": offset
            },
            message="Memories retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to search memories"
        )


@router.post("/search/similarity")
async def search_similar_memories(
    user_id: str,
    query: str,
    top_k: int = Query(10, ge=1, le=50, description="Number of similar memories to return"),
    memory_type: Optional[MemoryType] = Query(None, description="Filter by memory type")
):
    """
    Search for memories similar to the query using semantic similarity.

    Args:
        user_id: ID of the user searching for memories
        query: Query text to find similar memories for
        top_k: Number of similar memories to return
        memory_type: Filter by specific memory type

    Returns:
        JSON response with similar memories and similarity scores
    """
    try:
        if not query or not query.strip():
            return create_error_response(
                message="Query is required for similarity search",
                status_code=400
            )

        # Prepare memory types filter
        memory_types = [memory_type] if memory_type else None

        # Perform similarity search
        similar_memories = await find_similar_memories(
            query_text=query,
            user_id=user_id,
            top_k=top_k
        )

        # Format results with scores
        results = []
        for memory, similarity_score in similar_memories:
            # Apply memory type filter if specified
            if memory_types and memory.memory_type not in [mt.value for mt in memory_types]:
                continue

            results.append({
                "id": memory.id,
                "content_preview": memory.content[:200] + "..." if len(memory.content) > 200 else memory.content,
                "memory_type": memory.memory_type,
                "tags": memory.tags,
                "similarity_score": float(similarity_score),
                "created_at": memory.created_at.isoformat()
            })

        return create_success_response(
            data={
                "results": results,
                "query": query,
                "top_k": top_k,
                "returned_count": len(results)
            },
            message="Similar memories retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to search for similar memories"
        )


@router.get("/stats/{user_id}")
async def get_memory_stats(
    user_id: str
):
    """
    Get statistics about a user's memories.

    Args:
        user_id: ID of the user to get memory statistics for

    Returns:
        JSON response with memory statistics
    """
    try:
        stats = await memory_storage_service.get_memory_stats(user_id)

        return create_success_response(
            data=stats,
            message="Memory statistics retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to retrieve memory statistics"
        )


@router.delete("/cleanup/expired")
async def cleanup_expired_memories_endpoint(
    user_id: Optional[str] = None
):
    """
    Clean up expired memories for a user or system-wide.

    Args:
        user_id: Optional user ID to clean up for (if None, cleans up system-wide)

    Returns:
        JSON response with cleanup statistics
    """
    try:
        count = await memory_cleanup_service.cleanup_expired_memories(user_id)

        message = f"{count} expired memories cleaned up"
        if user_id:
            message += f" for user {user_id}"
        else:
            message += " system-wide"

        return create_success_response(
            data={
                "memories_cleaned": count
            },
            message=message
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to clean up expired memories"
        )


@router.post("/bulk-delete-by-tags")
async def bulk_delete_memories_by_tags(
    user_id: str,
    tags: List[str]
):
    """
    Delete all memories with specific tags.

    Args:
        user_id: ID of the user whose memories to delete
        tags: List of tags to match for deletion

    Returns:
        JSON response with deletion statistics
    """
    try:
        if not tags:
            return create_error_response(
                message="At least one tag must be specified for bulk deletion",
                status_code=400
            )

        deleted_count = await memory_storage_service.delete_memories_by_tags(user_id, tags)

        return create_success_response(
            data={
                "memories_deleted": deleted_count,
                "tags_affected": tags
            },
            message=f"{deleted_count} memories deleted with tags: {', '.join(tags)}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to bulk delete memories by tags"
        )


# Register the router in the main app
def register_memory_routes(app):
    """
    Register memory routes with the main application.

    Args:
        app: The FastAPI application instance
    """
    app.include_router(router)