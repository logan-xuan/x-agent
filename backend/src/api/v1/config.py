"""Configuration API endpoints."""

import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional

from ...config.manager import ConfigManager
from ...config.validator import validate_config
from ...services.llm.circuit_breaker import circuit_breaker_manager
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ConfigReloadResponse(BaseModel):
    """Response for config reload."""
    success: bool
    message: str
    models_count: int


class ConfigValidationResponse(BaseModel):
    """Response for config validation."""
    is_valid: bool
    errors: list[dict]
    warnings: list[dict]


class ProviderStatus(BaseModel):
    """Status of a single provider."""
    name: str
    model_id: str
    is_primary: bool
    is_healthy: bool
    circuit_state: str
    stats: dict


class ConfigStatusResponse(BaseModel):
    """Full configuration status."""
    providers: list[ProviderStatus]
    circuit_breakers: dict[str, dict]


class EditableModelConfig(BaseModel):
    """Editable model configuration."""
    name: str
    provider: str
    base_url: str
    api_key_masked: str  # Masked for display
    model_id: str
    is_primary: bool
    timeout: float
    max_retries: int
    priority: int


class EditableConfigResponse(BaseModel):
    """Editable configuration response."""
    models: list[EditableModelConfig]
    config_path: str


class UpdateModelRequest(BaseModel):
    """Request to update a model configuration."""
    model_id: Optional[str] = None
    api_key: Optional[str] = None  # New API key (optional)
    is_primary: Optional[bool] = None
    timeout: Optional[float] = Field(default=None, ge=5.0, le=300.0)
    max_retries: Optional[int] = Field(default=None, ge=0, le=5)
    priority: Optional[int] = Field(default=None, ge=0)


class UpdateModelResponse(BaseModel):
    """Response for model update."""
    success: bool
    message: str
    model: EditableModelConfig


@router.get("/config/status", response_model=ConfigStatusResponse)
async def get_config_status() -> ConfigStatusResponse:
    """Get current configuration status including provider health.
    
    Returns:
        Configuration status with provider health and circuit breaker states
    """
    config_manager = ConfigManager()
    config = config_manager.config
    
    providers = []
    
    # Get LLM router from app state or create one
    from ...main import get_llm_router
    llm_router = get_llm_router()
    
    # Get persistent stats from stat service
    persistent_stats = {}
    try:
        from ...services.stat_service import get_stat_service
        stat_service = get_stat_service()
        provider_stats = await stat_service.get_stats_by_provider()
        for ps in provider_stats:
            persistent_stats[ps["provider_name"]] = ps
    except Exception as e:
        logger.warning(
            "Failed to get persistent stats",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
    
    for model in config.models:
        # Get circuit breaker for this provider
        cb = circuit_breaker_manager.get_breaker(model.name)
        cb_status = cb.to_dict()
        
        # Merge persistent stats with in-memory stats
        stats = cb_status["stats"].copy()
        if model.name in persistent_stats:
            ps = persistent_stats[model.name]
            # Use persistent stats as primary source
            stats["total_requests"] = ps["total_requests"]
            stats["successful_requests"] = ps["successful_requests"]
            stats["failed_requests"] = ps["failed_requests"]
            stats["success_rate"] = ps["success_rate"]
            stats["avg_latency_ms"] = ps["avg_latency_ms"]
        
        # Check provider health
        is_healthy = True
        if llm_router:
            try:
                health_results = await llm_router.health_check()
                is_healthy = health_results.get(model.name, False)
            except Exception as e:
                logger.warning(
                    "Health check failed for model",
                    extra={
                        "model_name": model.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                is_healthy = False
        
        providers.append(ProviderStatus(
            name=model.name,
            model_id=model.model_id,
            is_primary=model.is_primary,
            is_healthy=is_healthy,
            circuit_state=cb_status["state"],
            stats=stats,
        ))
    
    return ConfigStatusResponse(
        providers=providers,
        circuit_breakers=circuit_breaker_manager.get_all_status(),
    )


@router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config() -> ConfigReloadResponse:
    """Reload configuration from file.
    
    Forces a reload of the configuration file and updates all services.
    
    Returns:
        Reload result with model count
    """
    config_manager = ConfigManager()
    
    try:
        # Force reload
        config_manager.reload()
        config = config_manager.config
        
        logger.info(
            "Configuration reloaded successfully",
            extra={
                "models_count": len(config.models),
            }
        )
        
        return ConfigReloadResponse(
            success=True,
            message=f"Configuration reloaded with {len(config.models)} models",
            models_count=len(config.models),
        )
    except Exception as e:
        logger.error(
            "Failed to reload configuration",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        raise HTTPException(status_code=500, detail=f"Failed to reload configuration: {e}")


@router.get("/config/validate", response_model=ConfigValidationResponse)
async def validate_current_config() -> ConfigValidationResponse:
    """Validate current configuration.
    
    Returns detailed validation results including errors and warnings.
    
    Returns:
        Validation result with errors and warnings
    """
    config_manager = ConfigManager()
    config = config_manager.config
    
    result = validate_config(config)
    
    return ConfigValidationResponse(
        is_valid=result.is_valid,
        errors=[
            {"field": e.field, "message": e.message, "suggestion": e.suggestion}
            for e in result.errors
        ],
        warnings=[
            {"field": w.field, "message": w.message, "suggestion": w.suggestion}
            for w in result.warnings
        ],
    )


@router.post("/config/circuit-breaker/{provider_name}/reset")
async def reset_circuit_breaker(provider_name: str) -> dict:
    """Reset circuit breaker for a specific provider.
    
    Args:
        provider_name: Name of the provider to reset
        
    Returns:
        Success message
    """
    breaker = circuit_breaker_manager.get_breaker(provider_name)
    breaker.reset()
    
    logger.info(
        "Circuit breaker reset for provider",
        extra={
            "provider_name": provider_name,
        }
    )
    
    return {"success": True, "message": f"Circuit breaker reset for {provider_name}"}


@router.post("/config/circuit-breaker/reset-all")
async def reset_all_circuit_breakers() -> dict:
    """Reset all circuit breakers.
    
    Returns:
        Success message
    """
    circuit_breaker_manager.reset_all()
    
    logger.info("All circuit breakers reset")
    
    return {"success": True, "message": "All circuit breakers reset"}


@router.get("/config/edit", response_model=EditableConfigResponse)
async def get_editable_config() -> EditableConfigResponse:
    """Get editable configuration.
    
    Returns configuration with masked API keys for editing.
    
    Returns:
        Editable configuration
    """
    config_manager = ConfigManager()
    config = config_manager.config
    
    models = []
    for model in config.models:
        models.append(EditableModelConfig(
            name=model.name,
            provider=model.provider,
            base_url=str(model.base_url),
            api_key_masked=model.get_masked_key(),
            model_id=model.model_id,
            is_primary=model.is_primary,
            timeout=model.timeout,
            max_retries=model.max_retries,
            priority=model.priority,
        ))
    
    return EditableConfigResponse(
        models=models,
        config_path=str(config_manager.config_path),
    )


@router.put("/config/models/{model_name}", response_model=UpdateModelResponse)
async def update_model_config(model_name: str, request: UpdateModelRequest) -> UpdateModelResponse:
    """Update a model configuration.
    
    Updates the configuration file and reloads.
    
    Args:
        model_name: Name of the model to update
        request: Update request with fields to change
        
    Returns:
        Updated model configuration
    """
    config_manager = ConfigManager()
    config = config_manager.config
    config_path = config_manager.config_path
    
    # Find the model
    model = config.get_model_by_name(model_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    
    # Read current YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config file: {e}")
    
    # Find and update the model in YAML
    models_list = yaml_data.get("models", [])
    model_found = False
    
    for i, m in enumerate(models_list):
        if m.get("name") == model_name:
            model_found = True
            # Update fields
            if request.model_id is not None:
                m["model_id"] = request.model_id
            if request.api_key is not None:
                m["api_key"] = request.api_key
            if request.is_primary is not None:
                # If setting this as primary, unset others
                if request.is_primary:
                    for other_m in models_list:
                        if other_m.get("name") != model_name:
                            other_m["is_primary"] = False
                m["is_primary"] = request.is_primary
            if request.timeout is not None:
                m["timeout"] = request.timeout
            if request.max_retries is not None:
                m["max_retries"] = request.max_retries
            if request.priority is not None:
                m["priority"] = request.priority
            break
    
    if not model_found:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found in config file")
    
    # Write back to YAML
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config file: {e}")
    
    # Reload configuration
    config_manager.reload()
    config = config_manager.config
    updated_model = config.get_model_by_name(model_name)
    
    if not updated_model:
        raise HTTPException(status_code=500, detail="Model disappeared after update")
    
    logger.info(
        "Model updated successfully",
        extra={
            "model_name": model_name,
        }
    )
    
    return UpdateModelResponse(
        success=True,
        message=f"Model '{model_name}' updated successfully",
        model=EditableModelConfig(
            name=updated_model.name,
            provider=updated_model.provider,
            base_url=str(updated_model.base_url),
            api_key_masked=updated_model.get_masked_key(),
            model_id=updated_model.model_id,
            is_primary=updated_model.is_primary,
            timeout=updated_model.timeout,
            max_retries=updated_model.max_retries,
            priority=updated_model.priority,
        ),
    )
