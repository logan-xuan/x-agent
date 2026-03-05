"""Skills API for managing and discovering skills.

This module provides REST API endpoints for:
- Listing available skills (with source filtering)
- Getting skill metadata
- Cache management
- Registry statistics
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Any
from pathlib import Path

from ...config.manager import ConfigManager
from ...models.skill import SkillSource
from ...services.skill.registry import (
    SkillRegistry,
    get_skill_registry,
    init_skill_registry,
)
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Module-level registry instance
_registry: SkillRegistry | None = None


def _get_registry() -> SkillRegistry:
    """Get or initialize the skill registry."""
    global _registry
    
    if _registry is None:
        config_manager = ConfigManager()
        workspace_path = Path(config_manager.config.workspace.path)
        
        # User skills directory from config
        user_skills_dir = workspace_path / config_manager.config.workspace.skills_dir
        
        # System skills directory
        backend_dir = Path(__file__).parent.parent.parent.parent
        system_skills_dir = backend_dir / "src" / "skills"
        
        _registry = init_skill_registry(
            user_skills_dir=user_skills_dir,
            system_skills_dir=system_skills_dir,
        )
        
        logger.info(
            "Skill registry initialized",
            extra={
                "user_skills_dir": str(user_skills_dir),
                "system_skills_dir": str(system_skills_dir),
            }
        )
    
    return _registry


@router.get("/skills")
async def list_skills(
    source: str | None = Query(
        None,
        description="Filter by source: 'user' or 'system'"
    ),
) -> list[dict[str, Any]]:
    """List all available skills.
    
    Returns skills from both USER and SYSTEM sources by default.
    USER skills override SYSTEM skills with the same skill_id.
    
    Args:
        source: Optional filter by source ('user' or 'system')
    
    Returns:
        List of skill information dictionaries
        
    Example:
        GET /api/v1/skills
        GET /api/v1/skills?source=user
    """
    try:
        registry = _get_registry()
        
        # Parse source filter
        source_filter: SkillSource | None = None
        if source:
            source_lower = source.lower()
            if source_lower == "user":
                source_filter = SkillSource.USER
            elif source_lower == "system":
                source_filter = SkillSource.SYSTEM
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid source: {source}. Use 'user' or 'system'."
                )
        
        skills = registry.list_skills(source=source_filter)
        
        logger.debug(
            "Listed skills",
            extra={
                "skill_count": len(skills),
                "source_filter": source,
            }
        )
        
        # Format response with new SkillManifest fields
        result = []
        for skill in skills:
            skill_source = registry.get_skill_source(skill.skill_id)
            result.append({
                "skill_id": skill.skill_id,
                "name": skill.name,
                "version": skill.version,
                "description": skill.description,
                "source": skill_source.name.lower() if skill_source else "unknown",
                "tags": skill.tags,
                "domains": skill.domains,
                "risk_level": skill.risk_level.value,
                "approval_mode": skill.approval_mode.value,
                "user_invocable": skill.user_invocable,
                "auto_trigger": skill.auto_trigger,
                "supports_dry_run": skill.supports_dry_run,
                "supports_rollback": skill.supports_rollback,
                "has_scripts": skill.has_scripts,
                "has_references": skill.has_references,
                "has_assets": skill.has_assets,
                "emoji": skill.emoji,
                "path": str(skill.path) if skill.path else None,
            })
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to list skills: {e}",
            extra={"error": str(e)},
            exc_info=True
        )
        return []


@router.post("/skills/cache/clear")
async def clear_cache() -> dict[str, Any]:
    """Clear the skill cache.
    
    Forces a reload of all skills on next access.
    Use this after adding or modifying skills.
    
    Returns:
        Success message
    """
    try:
        registry = _get_registry()
        registry.clear_cache()
        
        logger.info("Skill cache cleared via API")
        
        return {
            "success": True,
            "message": "Skill cache cleared. Skills will be reloaded on next access.",
        }
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/skills/stats")
async def get_stats() -> dict[str, Any]:
    """Get skill registry statistics.
    
    Returns:
        Dictionary with registry statistics including:
        - total_count: Total number of skills
        - user_count: Number of USER skills
        - system_count: Number of SYSTEM skills
        - cache_valid: Whether cache is currently valid
        - last_scan_time: Last cache refresh time
    """
    try:
        registry = _get_registry()
        stats = registry.get_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/skills/discover")
async def discover_skills(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """Discover relevant skills based on user intent.
    
    Uses semantic search and keyword matching to find the most
    relevant skills for a given query.
    
    Args:
        request: Request body containing:
            - query: Natural language query (required)
            - top_k: Maximum results (default: 10)
            - domains: Filter by domains (optional)
            - available_params: Available parameters (optional)
            
    Returns:
        List of SkillCard dictionaries sorted by relevance
        
    Example:
        POST /api/v1/skills/discover
        {
            "query": "convert document to pdf",
            "top_k": 5,
            "available_params": {"file": "report.md"}
        }
    """
    from ...models.skill import SkillSearchContext
    from ...services.skill.discovery import SkillDiscovery
    
    try:
        registry = _get_registry()
        
        # Extract request parameters
        query = request.get("query", "")
        if not query:
            raise HTTPException(
                status_code=400,
                detail="'query' is required"
            )
        
        top_k = request.get("top_k", 10)
        domains = request.get("domains")
        available_params = request.get("available_params", {})
        permissions = request.get("permissions", [])
        
        # Create search context
        context = SkillSearchContext(
            user_input=query,
            available_params=available_params,
            user_permissions=permissions,
        )
        
        # Create discovery service
        discovery = SkillDiscovery(registry=registry)
        
        # Discover skills
        results = discovery.discover(
            context=context,
            top_k=top_k,
            domains=domains,
        )
        
        logger.info(
            f"Discovered {len(results)} skills",
            extra={
                "query": query[:50],
                "top_k": top_k,
                "results": [r.skill_id for r in results],
            }
        )
        
        # Convert to dict
        return [r.to_dict() for r in results]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to discover skills: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to discover skills: {str(e)}"
        )


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    """Get detailed information about a specific skill.
    
    Args:
        skill_id: Skill identifier (kebab-case)
        
    Returns:
        Complete skill manifest as dictionary
        
    Raises:
        HTTPException: 404 if skill not found
    """
    try:
        registry = _get_registry()
        
        entry = registry.get_skill_with_source(skill_id)
        
        if not entry:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_id}' not found"
            )
        
        skill, source = entry
        
        return {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "version": skill.version,
            "vendor": skill.vendor,
            "description": skill.description,
            "description_detail": skill.description_detail,
            "source": source.name.lower(),
            "tags": skill.tags,
            "domains": skill.domains,
            "examples": skill.examples,
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "timeout_ms": skill.timeout_ms,
            "max_retries": skill.max_retries,
            "idempotency": skill.idempotency,
            "risk_level": skill.risk_level.value,
            "data_access": skill.data_access.value,
            "side_effect": skill.side_effect,
            "approval_mode": skill.approval_mode.value,
            "user_invocable": skill.user_invocable,
            "auto_trigger": skill.auto_trigger,
            "supports_dry_run": skill.supports_dry_run,
            "supports_rollback": skill.supports_rollback,
            "has_scripts": skill.has_scripts,
            "has_references": skill.has_references,
            "has_assets": skill.has_assets,
            "emoji": skill.emoji,
            "homepage": skill.homepage,
            "path": str(skill.path) if skill.path else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


# =============================================================================
# Legacy API Compatibility
# =============================================================================


@router.post("/skills/{skill_id}/invoke")
async def invoke_skill(
    skill_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Invoke a skill with arguments.
    
    Note: This is a placeholder for Phase 5-6 implementation.
    Currently returns skill info without executing.
    
    Args:
        skill_id: Skill identifier
        request: Request body containing:
            - arguments: Command arguments (optional)
            - session_id: Session ID for tracking (optional)
            
    Returns:
        Invocation result with skill info
    """
    try:
        registry = _get_registry()
        skill = registry.get_skill(skill_id)
        
        if not skill:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_id}' not found"
            )
        
        arguments = request.get("arguments", "")
        session_id = request.get("session_id", "default")
        
        command = f"/{skill_id}"
        if arguments:
            command += f" {arguments}"
        
        return {
            "success": True,
            "message": f"Skill '{skill_id}' invocation initiated",
            "session_id": session_id,
            "command": command,
            "skill_info": {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "risk_level": skill.risk_level.value,
                "approval_mode": skill.approval_mode.value,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invoke skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to invoke skill: {str(e)}")
