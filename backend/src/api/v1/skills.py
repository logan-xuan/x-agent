"""Skills API for managing and invoking skills.

This module provides REST API endpoints for:
- Listing available skills
- Getting skill metadata
- Invoking skills with arguments
"""

from fastapi import APIRouter, HTTPException
from typing import Any
from pathlib import Path

from ...config.manager import ConfigManager
from ...services.skill_registry import SkillRegistry, get_skill_registry
from ...models.skill import SkillMetadata

router = APIRouter()


@router.get("/skills")
async def list_skills() -> list[dict[str, Any]]:
    """List all available skills with Phase 2 metadata.
    
    Returns:
        List of skill information dictionaries
        
    Example:
        GET /api/skills
        
        Response:
        [
            {
                "name": "pptx",
                "description": "Presentation creation...",
                "argument_hint": "[command] [filename]",
                "allowed_tools": ["read_file", "write_file"],
                "user_invocable": true,
                "has_scripts": true,
                "has_references": false,
                "has_assets": false
            }
        ]
    """
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
    
    try:
        # Get skill registry from global instance
        config_manager = ConfigManager()
        workspace_path = Path(config_manager.config.workspace.path)
        registry = get_skill_registry(workspace_path)
        
        skills = registry.list_all_skills()
        
        logger.debug(
            "Listed skills",
            extra={
                "skill_count": len(skills),
            }
        )
        
        # Filter and format skills
        return [
            {
                "name": s.name,
                "description": s.description,
                "argument_hint": s.argument_hint,
                "allowed_tools": s.allowed_tools,
                "user_invocable": s.user_invocable,
                "disable_model_invocation": s.disable_model_invocation,
                "has_scripts": s.has_scripts,
                "has_references": s.has_references,
                "has_assets": s.has_assets,
                "context": s.context,
                "license": s.license,
                "path": str(s.path),
            }
            for s in skills
        ]
        
    except Exception as e:
        logger.error(
            f"Failed to list skills: {e}",
            extra={"error": str(e)},
            exc_info=True
        )
        # Return empty list instead of 500 error for better UX
        return []


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str) -> dict[str, Any]:
    """Get detailed information about a specific skill.
    
    Args:
        skill_name: Name of the skill
        
    Returns:
        Skill information dictionary
        
    Raises:
        HTTPException: If skill not found
    """
    try:
        config_manager = ConfigManager()
        workspace_path = Path(config_manager.config.workspace.path)
        registry = get_skill_registry(workspace_path)
        
        skill = registry.get_skill_metadata(skill_name)
        
        if not skill:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_name}' not found"
            )
        
        return {
            "name": skill.name,
            "description": skill.description,
            "argument_hint": skill.argument_hint,
            "allowed_tools": skill.allowed_tools,
            "user_invocable": skill.user_invocable,
            "disable_model_invocation": skill.disable_model_invocation,
            "has_scripts": skill.has_scripts,
            "has_references": skill.has_references,
            "has_assets": skill.has_assets,
            "context": skill.context,
            "license": skill.license,
            "path": str(skill.path),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.post("/skills/{skill_name}/invoke")
async def invoke_skill(
    skill_name: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Invoke a skill with arguments (Phase 2).
    
    This endpoint allows direct skill invocation via API.
    The actual execution happens through the Orchestrator.
    
    Args:
        skill_name: Name of the skill to invoke
        request: Request body containing:
            - arguments: Command arguments (optional)
            - session_id: Session ID for tracking (optional)
            
    Returns:
        Invocation result with session_id for tracking
        
    Example:
        POST /api/skills/pptx/invoke
        {
            "arguments": "create presentation.pptx",
            "session_id": "session-123"
        }
    """
    try:
        # Validate skill exists
        config_manager = ConfigManager()
        workspace_path = Path(config_manager.config.workspace.path)
        registry = get_skill_registry(workspace_path)
        
        skill = registry.get_skill_metadata(skill_name)
        
        if not skill:
            raise HTTPException(
                status_code=404,
                detail=f"Skill '{skill_name}' not found"
            )
        
        # Extract arguments
        arguments = request.get("arguments", "")
        session_id = request.get("session_id", "default")
        
        # Build command string
        command = f"/{skill_name}"
        if arguments:
            command += f" {arguments}"
        
        return {
            "success": True,
            "message": f"Skill '{skill_name}' invocation initiated",
            "session_id": session_id,
            "command": command,
            "skill_info": {
                "name": skill.name,
                "description": skill.description,
                "argument_hint": skill.argument_hint,
                "allowed_tools": skill.allowed_tools,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invoke skill: {str(e)}")
